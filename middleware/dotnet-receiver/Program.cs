using System.Collections.Concurrent;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
using Mex.Journal.Recon;

// MEX Signaal-endpoint (Fase D) — één alert-URL per chart.
// Fase C deed: intent opslaan, MFE/MAE oogsten, Discord-relay.
// Fase D voegt toe: de TRECHTER. Elke route die je in het Pine-script aanvinkt
// stuurt zijn eigen alert() naar DEZELFDE webhook-URL; hier herkennen we per
// bericht het type en sturen het naar de juiste bestemming:
//   PMT-JSON          -> door naar PMT (Tradovate of Rithmic)
//   Discord-embed     -> 1:1 door naar de Discord-webhook
//   PineConnector-cmd -> door naar de PineConnector-webhook
//   journal-CSV       -> alleen opslaan
//   overig (Fase C)   -> bestaand gedrag: intent opslaan + Discord-melding
// Alles wordt append-only gejournald. Standaard staat DRY_RUN AAN: er wordt
// niets doorgestuurd tot je MEX_DRY_RUN=false zet.

var builder = WebApplication.CreateBuilder(args);
var app = builder.Build();

var cfg = app.Configuration.GetSection("Mex");
var secret = Environment.GetEnvironmentVariable("MEX_WEBHOOK_SECRET")
    ?? cfg["SharedSecret"] ?? "";
var storePath = cfg["IntentStorePath"] ?? "/root/intent-store";
var discordEnv = cfg["DiscordWebhookEnvVar"] ?? "MEX_DISCORD_WEBHOOK";
var pmtUrl = Environment.GetEnvironmentVariable("MEX_PMT_URL") ?? cfg["PmtUrl"] ?? "";
var pmtRithmicUrl = Environment.GetEnvironmentVariable("MEX_PMT_RITHMIC_URL") ?? cfg["PmtRithmicUrl"] ?? "";
var pcUrl = Environment.GetEnvironmentVariable("MEX_PC_URL") ?? cfg["PineConnectorUrl"] ?? "";
// Veilig standaard: alleen doorsturen als je expliciet MEX_DRY_RUN=false zet.
var dryRun = !string.Equals(Environment.GetEnvironmentVariable("MEX_DRY_RUN") ?? "true",
                            "false", StringComparison.OrdinalIgnoreCase);
Directory.CreateDirectory(storePath);

var http = new HttpClient { Timeout = TimeSpan.FromSeconds(10) };
var seen = new ConcurrentDictionary<string, DateTime>();   // idempotency

app.MapGet("/health", () => Results.Ok(new
{
    status = "alive",
    ts = DateTime.UtcNow,
    dryRun,
    armed = Runtime.Armed,
    pmtConfigured = !string.IsNullOrEmpty(pmtUrl)
}));

// Kill-switch: POST /killswitch?token=<secret>&armed=false  -> geen entries meer door.
// Exits worden NOOIT geblokkeerd, ook niet als disarmed.
app.MapPost("/killswitch", (string token, bool armed) =>
{
    if (string.IsNullOrEmpty(secret) || token != secret) return Results.Unauthorized();
    Runtime.Armed = armed;
    return Results.Ok(new { armed = Runtime.Armed });
});

app.MapPost("/signal/{token}", async (string token, HttpContext ctx) =>
{
    if (string.IsNullOrEmpty(secret) || token != secret)
        return Results.Unauthorized();

    string body;
    using (var reader = new StreamReader(ctx.Request.Body))
        body = await reader.ReadToEndAsync();
    if (string.IsNullOrWhiteSpace(body)) return Results.BadRequest("empty");

    // --- idempotency: TradingView (of een netwerk-retry) levert soms dubbel ---
    var hash = Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(body)));
    var now = DateTime.UtcNow;
    foreach (var kv in seen)
        if ((now - kv.Value).TotalSeconds > 5) seen.TryRemove(kv.Key, out _);
    if (!seen.TryAdd(hash, now))
        return Results.Ok(new { accepted = true, handled = false, reason = "duplicate" });

    JsonNode? node = null;
    try { node = JsonNode.Parse(body); } catch { /* geen JSON: tekstroutes hieronder */ }
    var obj = node as JsonObject;

    // ---------------------------------------------------------------- PMT ---
    // Let op: PMT-Tradovate en PMT-Rithmic sturen een IDENTIEKE payload, dus de
    // broker is niet uit het bericht af te leiden. We kiezen op account-id:
    // MEX_PMT_RITHMIC_ACCOUNTS (kommalijst) gaat naar de Rithmic-endpoint.
    if (obj is not null &&
        (obj.ContainsKey("multiple_accounts") || (obj.ContainsKey("token") && obj.ContainsKey("data"))))
    {
        var action = (obj["data"]?.ToString() ?? "").ToLowerInvariant();
        var isEntry = action == "buy" || action == "sell";
        var acct = "";
        if (obj["multiple_accounts"] is JsonArray arr && arr.Count > 0 && arr[0] is JsonObject a0)
            acct = a0["account_id"]?.ToString() ?? "";

        if (isEntry && !Runtime.Armed)
        {
            await AppendAsync(storePath, "pmt", body, "blocked: kill-switch");
            return Results.Ok(new { accepted = true, handled = false, reason = "kill-switch: disarmed" });
        }

        var rithmicList = Environment.GetEnvironmentVariable("MEX_PMT_RITHMIC_ACCOUNTS") ?? "";
        var useRithmic = !string.IsNullOrWhiteSpace(rithmicList) && !string.IsNullOrEmpty(acct)
            && rithmicList.Split(',').Select(x => x.Trim()).Contains(acct);
        var target = useRithmic && !string.IsNullOrEmpty(pmtRithmicUrl) ? pmtRithmicUrl : pmtUrl;

        var res = await ForwardJsonAsync(http, target, body, dryRun);
        await AppendAsync(storePath, "pmt", body, res, acct);
        return Results.Ok(new { accepted = true, kind = "pmt", account = Tail(acct), result = res });
    }

    // ------------------------------------------------------------ Discord ---
    if (obj is not null && (obj.ContainsKey("embeds") || obj.ContainsKey("content")))
    {
        var url = Environment.GetEnvironmentVariable(discordEnv) ?? "";
        var res = await ForwardJsonAsync(http, url, body, dryRun);
        await AppendAsync(storePath, "discord", body, res);
        return Results.Ok(new { accepted = true, kind = "discord", result = res });
    }

    // ---------------------------------------------------- journal (CSV) ----
    if (obj is not null && (obj["type"]?.ToString() == "journal" || obj.ContainsKey("csv")))
    {
        await AppendAsync(storePath, "journal", obj["csv"]?.ToString() ?? body, "stored");
        return Results.Ok(new { accepted = true, kind = "journal", stored = true });
    }

    // ------------------------------------------------- PineConnector (txt) --
    if (obj is null)
    {
        var parts = body.Split(',').Select(p => p.Trim()).ToArray();
        if (parts.Length >= 3 &&
            (parts[1].Equals("buy", StringComparison.OrdinalIgnoreCase) ||
             parts[1].Equals("sell", StringComparison.OrdinalIgnoreCase) ||
             parts[1].Equals("exit", StringComparison.OrdinalIgnoreCase)))
        {
            var isEntry = !parts[1].Equals("exit", StringComparison.OrdinalIgnoreCase);
            if (isEntry && !Runtime.Armed)
                return Results.Ok(new { accepted = true, handled = false, reason = "kill-switch: disarmed" });
            var res = await ForwardTextAsync(http, pcUrl, body, dryRun);
            await AppendAsync(storePath, "pineconnector", body, res);
            return Results.Ok(new { accepted = true, kind = "pineconnector", result = res });
        }
        // CSV-journalregel van de Journal-route
        if (parts.Length >= 10)
        {
            await AppendAsync(storePath, "journal", body, "stored");
            return Results.Ok(new { accepted = true, kind = "journal", stored = true });
        }
        await AppendAsync(storePath, "unknown", body, "stored");
        return Results.Ok(new { accepted = true, kind = "unknown", stored = true });
    }

    // ------------------------------------------- Fase C: bestaand gedrag ----
    var intent = new SignalIntent
    {
        ReceivedUtc = DateTime.UtcNow,
        Account = node?["account"]?.GetValue<string>() ?? node?["acc"]?.GetValue<string>() ?? "",
        Symbol = node?["symbol"]?.GetValue<string>() ?? node?["ticker"]?.GetValue<string>() ?? "",
        Action = node?["action"]?.GetValue<string>() ?? node?["side"]?.GetValue<string>() ?? "",
        Price = TryDec(node?["price"]) ?? TryDec(node?["signalPrice"]),
        RunUp = TryDec(node?["runup"]) ?? TryDec(node?["mfe"]),
        Drawdown = TryDec(node?["drawdown"]) ?? TryDec(node?["mae"]),
        RawJson = body,
    };

    var file = Path.Combine(storePath, $"intents_{DateTime.UtcNow:yyyyMMdd}.jsonl");
    await File.AppendAllTextAsync(file, JsonSerializer.Serialize(intent) + "\n");

    var msg = $"**{intent.Action}** {intent.Symbol} · acct {Tail(intent.Account)}" +
        (intent.Price is { } p ? $" @ {p}" : "") +
        (intent.RunUp is { } ru ? $" · RunUp {ru}" : "") +
        (intent.Drawdown is { } dd ? $" · DD {dd}" : "");
    await DiscordNotifier.PostAsync(discordEnv, "📡 MEX Signaal", msg, 3447003);

    return Results.Ok(new { stored = true, account = intent.Account });
});

app.Run();

// --- helpers ---------------------------------------------------------------

// Append-only audit: één regel per binnengekomen bericht, per dag één bestand.
static async Task AppendAsync(string storePath, string kind, string body, string result, string account = "")
{
    var rec = JsonSerializer.Serialize(new
    {
        ts = DateTime.UtcNow,
        kind,
        account,
        result,
        body = body.Length > 4000 ? body[..4000] : body
    });
    var file = Path.Combine(storePath, $"routed_{DateTime.UtcNow:yyyyMMdd}.jsonl");
    await File.AppendAllTextAsync(file, rec + "\n");
}

// POST met retry op netwerkfouten en 5xx; 4xx niet opnieuw proberen (lost niet op).
static async Task<string> ForwardJsonAsync(HttpClient http, string url, string json, bool dryRun)
    => await ForwardAsync(http, url, json, "application/json", dryRun);

static async Task<string> ForwardTextAsync(HttpClient http, string url, string text, bool dryRun)
    => await ForwardAsync(http, url, text, "text/plain", dryRun);

static async Task<string> ForwardAsync(HttpClient http, string url, string payload, string contentType, bool dryRun)
{
    if (dryRun) return $"dry_run -> {(string.IsNullOrEmpty(url) ? "(geen url)" : url)}";
    if (string.IsNullOrEmpty(url)) return "error: doel-url niet geconfigureerd";

    for (var attempt = 1; attempt <= 3; attempt++)
    {
        try
        {
            using var content = new StringContent(payload, Encoding.UTF8, contentType);
            var resp = await http.PostAsync(url, content);
            var code = (int)resp.StatusCode;
            if (code < 400) return $"sent {code} (poging {attempt})";
            if (code < 500) return $"error {code} (4xx, niet opnieuw)";
        }
        catch (Exception ex)
        {
            if (attempt == 3) return $"error {ex.GetType().Name}";
        }
        await Task.Delay(TimeSpan.FromMilliseconds(500 * Math.Pow(2, attempt - 1)));
    }
    return "error: retries op";
}

static decimal? TryDec(JsonNode? n)
{
    if (n == null) return null;
    try { return n.GetValue<decimal>(); }
    catch { return decimal.TryParse(n.ToString(), out var d) ? d : null; }
}
static string Tail(string s) => s.Length >= 5 ? s[^5..] : s;

public static class Runtime
{
    public static volatile bool Armed = true;
}

public class SignalIntent
{
    public DateTime ReceivedUtc { get; set; }
    public string Account { get; set; } = "";
    public string Symbol { get; set; } = "";
    public string Action { get; set; } = "";
    public decimal? Price { get; set; }
    public decimal? RunUp { get; set; }
    public decimal? Drawdown { get; set; }
    public string RawJson { get; set; } = "";
}
