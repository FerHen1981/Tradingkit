using System.Collections.Concurrent;
using System.Diagnostics;
using System.Net;
using System.Net.Http.Headers;
using System.Net.Sockets;
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

// Kaart-rendering: Discord-berichten van Tier A/B gaan als PNG i.p.v. tekst.
// Zelf-configurerend: staat het render-script er niet, dan blijft alles tekst.
var renderScript = Environment.GetEnvironmentVariable("MEX_RENDER_SCRIPT")
    ?? cfg["RenderScript"] ?? "/root/mex-renderer/render-signal.js";
var renderEnabled = File.Exists(renderScript) &&
    !string.Equals(Environment.GetEnvironmentVariable("MEX_RENDER_ENABLED"), "false",
                   StringComparison.OrdinalIgnoreCase);
CardRender.Node = Environment.GetEnvironmentVariable("MEX_NODE") ?? "node";
CardRender.Script = renderScript;
CardRender.OutDir = Environment.GetEnvironmentVariable("MEX_RENDER_OUT_DIR") ?? "/tmp/mex-cards";
CardRender.TimeoutMs = int.TryParse(Environment.GetEnvironmentVariable("MEX_RENDER_TIMEOUT_MS"), out var rt) ? rt : 30000;
CardRender.Keep = string.Equals(Environment.GetEnvironmentVariable("MEX_RENDER_KEEP"), "true",
                                StringComparison.OrdinalIgnoreCase);
CardTier.LoadOverrides(Environment.GetEnvironmentVariable("MEX_CARD_TIER_OVERRIDES") ?? "");
if (renderEnabled) Directory.CreateDirectory(CardRender.OutDir);

// PMT laat alleen geregistreerde IP-adressen toe ("valid ip not found in pool").
// Deze server heeft zowel IPv4 als IPv6; ging het verkeer via IPv6 naar buiten, dan
// zag PMT een adres dat niet in de pool staat en werd de order geweigerd — zonder
// dat je dat aan de statuscode kon zien. Hier binden we uitgaand verkeer aan IPv4,
// zodat er precies één adres te whitelisten valt. Dit doet hetzelfde als de
// precedence-regel in /etc/gai.conf, maar dan zo dat een herinstallatie van de
// server het niet stilletjes terugdraait. Uit te zetten met MEX_FORCE_IPV4=false.
var forceIpv4 = !string.Equals(Environment.GetEnvironmentVariable("MEX_FORCE_IPV4"),
                               "false", StringComparison.OrdinalIgnoreCase);
var handler = new SocketsHttpHandler();
if (forceIpv4)
    handler.ConnectCallback = async (ctx, ct) =>
    {
        var addrs = await Dns.GetHostAddressesAsync(ctx.DnsEndPoint.Host,
                                                    AddressFamily.InterNetwork, ct);
        if (addrs.Length == 0)
            throw new SocketException((int)SocketError.HostNotFound);
        var socket = new Socket(AddressFamily.InterNetwork, SocketType.Stream, ProtocolType.Tcp)
        {
            NoDelay = true
        };
        try
        {
            await socket.ConnectAsync(addrs, ctx.DnsEndPoint.Port, ct);
            return new NetworkStream(socket, ownsSocket: true);
        }
        catch
        {
            socket.Dispose();
            throw;
        }
    };
var http = new HttpClient(handler) { Timeout = TimeSpan.FromSeconds(30) };
var seen = new ConcurrentDictionary<string, DateTime>();   // idempotency

app.MapGet("/health", () => Results.Ok(new
{
    status = "alive",
    ts = DateTime.UtcNow,
    dryRun,
    armed = Runtime.Armed,
    pmtConfigured = !string.IsNullOrEmpty(pmtUrl),
    renderEnabled,
    renderScript
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

        // D-53 · qty-map per account. Pine zet quantity_multiplier op 1; hier overschrijven
        // we die met wat de map voor dit account voorschrijft. Ontbreekt het account in
        // de map, dan laten we de payload precies zoals Pine hem stuurt. Bron: env
        // MEX_ACCOUNT_QTY_MULTIPLIERS (kommalijst account_id=n). Vers account = 1.
        var qtyMult = AccountQtyMap.MultiplierFor(acct);
        if (qtyMult is int m && a0 is not null)
        {
            a0["quantity_multiplier"] = m;
            body = node!.ToJsonString();     // rebuild — de forward stuurt deze gewijzigde body
        }

        // D-40 · reactieve blocked-gate per account. Een eerdere PMT-weigering met een
        // day-cap/DLL/payout-cap marker houdt dit account dicht tot de eerstvolgende
        // 18:00 ET sessie-roll. Dezelfde plek en vorm als de kill-switch hierboven.
        // Alleen entries; een exit moet nog door zodat een openstaande positie kán sluiten.
        if (isEntry && !string.IsNullOrEmpty(acct) && AccountBlockGate.IsBlocked(acct, DateTime.UtcNow))
        {
            var was = AccountBlockGate.ReasonFor(acct);
            var msg = $"GEWEIGERD lokaal — day-cap/DLL blokkade actief (eerder: {was})";
            await AppendAsync(storePath, "pmt", body, msg, acct);
            await DiscordNotifier.PostAsync(discordEnv, "⛔ Order NIET geplaatst",
                $"{action.ToUpperInvariant()} · account {Tail(acct)}\n{msg}", 14701138);
            return Results.Ok(new { accepted = true, kind = "pmt", account = Tail(acct), result = msg, blocked = true });
        }

        var rithmicList = Environment.GetEnvironmentVariable("MEX_PMT_RITHMIC_ACCOUNTS") ?? "";
        var useRithmic = !string.IsNullOrWhiteSpace(rithmicList) && !string.IsNullOrEmpty(acct)
            && rithmicList.Split(',').Select(x => x.Trim()).Contains(acct);
        var target = useRithmic && !string.IsNullOrEmpty(pmtRithmicUrl) ? pmtRithmicUrl : pmtUrl;

        var res = await ForwardJsonAsync(http, target, body, dryRun);
        await AppendAsync(storePath, "pmt", body, res, acct);

        // D-40 · registreer de weigering. Als PMT afwees met een day-cap/DLL marker in de
        // reply, dan gaat dit account op slot tot 18:00 ET. Reactief, met opzet: de eerste
        // order na de weigering vertrok al — die is nu geweigerd — daarna is het dicht.
        if (res.StartsWith("GEWEIGERD") && !string.IsNullOrEmpty(acct))
            AccountBlockGate.RegisterIfLimitMarker(acct, res, DateTime.UtcNow);

        // Een geweigerde order is stil: er komt geen fill, geen exit, geen kaart.
        // Zonder melding merk je het pas als je het bij de broker gaat zoeken.
        if (res.StartsWith("GEWEIGERD") || res.StartsWith("error"))
            await DiscordNotifier.PostAsync(discordEnv, "⛔ Order NIET geplaatst",
                $"{action.ToUpperInvariant()} · account {Tail(acct)}\n{res}", 14701138);

        return Results.Ok(new { accepted = true, kind = "pmt", account = Tail(acct), result = res });
    }

    // ------------------------------------------------------------ Discord ---
    if (obj is not null && (obj.ContainsKey("embeds") || obj.ContainsKey("content")))
    {
        var title = obj["embeds"]?[0]?["title"]?.ToString() ?? "";
        var tier = CardTier.For(title);

        // D-28/2 — per-kanaal routing. Funded, eval en per-firm kunnen elk hun eigen
        // webhook krijgen; is er niets gezet, dan blijft MEX_DISCORD_WEBHOOK het doel en
        // verandert er niets aan een bestaande installatie.
        var account = NotifyRoute.AccountFrom(obj);
        var routed = NotifyRoute.WebhookFor(account, "trade", "discord");
        var url = routed.Length > 0 ? routed : (Environment.GetEnvironmentVariable(discordEnv) ?? "");


        // SIGNAL BLOCKED is hoogfrequent: tijdens een day halt wordt élk signaal
        // geblokkeerd, dus zonder poort loopt het kanaal vol met hetzelfde bericht.
        // Nieuws is alleen: dit account handelt vandaag (of helemaal) niet meer —
        // en dat hoeft één keer. Routineblokkades (time gate, stop invalid, ...)
        // worden gedempt; ze blijven wel in het journaal staan.
        if (!CardTier.HasOverride(title) && BlockedGate.Applies(title))
        {
            var desc = obj["embeds"]?[0]?["description"]?.ToString() ?? "";
            if (!BlockedGate.Admit(title, desc))
            {
                await AppendAsync(storePath, "discord", body, "blocked-notice suppressed");
                return Results.Ok(new { accepted = true, kind = "discord", suppressed = true });
            }
            tier = 'B';   // eerste terminale blokkade van deze handelsdag: wél een kaart
        }

        // D-28/6 — Telegram-pariteit. Ná de blocked-poort: wat Discord niet mag halen,
        // mag Telegram ook niet halen. De payload draagt al {content, text}, dus dezelfde
        // body volstaat voor beide kanten.
        var telegram = NotifyRoute.WebhookFor(account, "trade", "telegram");
        if (telegram.Length > 0 && telegram != url)
            _ = Task.Run(() => ForwardJsonAsync(http, telegram, body, dryRun));

        // Tier A/B krijgt een kaart. Renderen duurt seconden, dus dat gebeurt in
        // de achtergrond: TradingView krijgt direct antwoord en probeert niet
        // opnieuw. Mislukt de render, dan gaat het originele bericht alsnog door.
        if (renderEnabled && tier != 'C')
        {
            // D-28/5 — rate-limit. Bij een burst kost elke kaart een Chromium-render plus
            // een post op een webhook die 30/min toestaat. Tier A gaat altijd door.
            int held;
            if (!PostRate.Allow(url, tier, out held))
            {
                await AppendAsync(storePath, "discord", body, $"card rate-limited (tier {tier})");
                return Results.Ok(new { accepted = true, kind = "discord", tier = tier.ToString(), rateLimited = true });
            }
            var note = held > 0 ? $" (+{held} gedempt)" : "";
            _ = Task.Run(() => CardRender.RenderAndPostAsync(http, url, body, title, storePath, dryRun));
            await AppendAsync(storePath, "discord", body, $"card queued (tier {tier}){note}");
            return Results.Ok(new { accepted = true, kind = "discord", tier = tier.ToString(), card = "queued", suppressedBefore = held });
        }

        var res = await ForwardJsonAsync(http, url, body, dryRun);
        await AppendAsync(storePath, "discord", body, res);
        return Results.Ok(new { accepted = true, kind = "discord", tier = tier.ToString(), result = res });
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
static Task AppendAsync(string storePath, string kind, string body, string result, string account = "")
    => Audit.AppendAsync(storePath, kind, body, result, account);

// POST met retry op netwerkfouten en 5xx; 4xx niet opnieuw proberen (lost niet op).
// Het antwoord kort houden: het gaat mee in elke journaalregel.
static string Excerpt(string s)
{
    s = (s ?? "").Replace('\n', ' ').Replace('\r', ' ').Trim();
    return s.Length <= 200 ? s : s[..200] + "…";
}

// Bewust conservatief: liever een geplaatste order die onterecht als verdacht wordt
// gemarkeerd, dan een geweigerde order die als geslaagd wegschrijft. Het volledige
// antwoord staat hoe dan ook in het journaal, dus deze lijst is aan te scherpen zodra
// we het echte antwoordformaat van PMT hebben gezien.
static bool Rejected(string reply)
{
    if (string.IsNullOrWhiteSpace(reply)) return false;
    var r = reply.ToLowerInvariant();
    string[] markers =
    {
        "not found in pool", "cannot place", "invalid ip", "unauthorized", "forbidden",
        "\"error\"", "\"success\":false", "\"status\":false", "not allowed", "rejected",
    };
    return markers.Any(m => r.Contains(m));
}

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
            // PMT antwoordt op een geweigerde order met 200 en de reden in de body.
            // Alleen naar de statuscode kijken schrijft zo'n weigering weg als
            // "sent 200" — niet te onderscheiden van een geplaatste order.
            var reply = Excerpt(await resp.Content.ReadAsStringAsync());
            if (code < 400)
                return Rejected(reply)
                    ? $"GEWEIGERD {code} door doelserver: {reply}"
                    : $"sent {code} (poging {attempt}){(reply.Length > 0 ? " · " + reply : "")}";
            if (code < 500) return $"error {code} (4xx, niet opnieuw): {reply}";
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

// D-53 · Per-account quantity_multiplier override. Pine schrijft die hard op 1;
// hier vertalen we per account naar een andere waarde. Env: MEX_ACCOUNT_QTY_MULTIPLIERS
// (kommalijst account_id=n). Ontbrekend account = payload niet aanraken. Handmatige
// map, geen fase-detectie — dat is v2 en vraagt echte accountstand uit de poller.
public static class AccountQtyMap
{
    static readonly Dictionary<string, int> _map = new(StringComparer.OrdinalIgnoreCase);

    static AccountQtyMap()
    {
        Load(Environment.GetEnvironmentVariable("MEX_ACCOUNT_QTY_MULTIPLIERS") ?? "");
    }

    // Herbouw de map — nuttig voor tests én voor een toekomstige reload zonder herstart.
    public static void Load(string spec)
    {
        _map.Clear();
        foreach (var part in (spec ?? "").Split(',', StringSplitOptions.RemoveEmptyEntries))
        {
            var kv = part.Split('=', 2);
            if (kv.Length == 2 && int.TryParse(kv[1].Trim(), out var n) && n > 0)
                _map[kv[0].Trim()] = n;
        }
    }

    public static int? MultiplierFor(string account)
        => !string.IsNullOrEmpty(account) && _map.TryGetValue(account, out var n) ? n : null;
}

// D-40 · Reactieve blocked-gate per account. Onthoudt een PMT-weigering met een
// day-cap / DLL / payout-cap marker tot de eerstvolgende sessie-roll (18:00 ET —
// zelfde grens die fills_pairing.session_date gebruikt). Bewust reactief: de eerste
// order na een weigering vertrekt nog en wordt door PMT afgewezen — daarna is het
// account dicht tot de nieuwe sessie. Een proactieve versie (echte dag-P&L per
// account uit de Tradovate-poller) is v2, dat vraagt de poller-data in de receiver.
public static class AccountBlockGate
{
    // Alleen markers die eenduidig "dag-limiet geraakt" betekenen. "rejected" en
    // "unauthorized" zijn te breed — die vallen elk 4xx onder en zouden een account
    // onterecht sluiten. Wat wél telt is het waarom.
    static readonly string[] LimitMarkers =
    {
        "day cap", "daily cap", "day loss", "daily loss", "dll", "loss limit",
        "payout cap", "payout limit", "profit target", "consistency", "max loss",
    };

    static readonly ConcurrentDictionary<string, (DateTime ExpiresUtc, string Reason)> _blocked = new();
    static readonly TimeZoneInfo _et = ResolveEt();

    static TimeZoneInfo ResolveEt()
    {
        // Linux draagt IANA-ids; Windows draagt de Engelse. Val netjes terug zodat het
        // niet uitmaakt waar dit ooit gebouwd wordt.
        try { return TimeZoneInfo.FindSystemTimeZoneById("America/New_York"); }
        catch { return TimeZoneInfo.FindSystemTimeZoneById("Eastern Standard Time"); }
    }

    // De eerstvolgende 18:00 ET in UTC — dezelfde grens die de dashboards en
    // session_date() aanhouden. Vóór 18:00 ET = vandaag 18:00 ET, ná = morgen.
    static DateTime NextSessionRollUtc(DateTime nowUtc)
    {
        var nowEt = TimeZoneInfo.ConvertTimeFromUtc(nowUtc, _et);
        var todayRollEt = new DateTime(nowEt.Year, nowEt.Month, nowEt.Day, 18, 0, 0, DateTimeKind.Unspecified);
        var rollEt = nowEt < todayRollEt ? todayRollEt : todayRollEt.AddDays(1);
        return TimeZoneInfo.ConvertTimeToUtc(rollEt, _et);
    }

    public static bool IsBlocked(string account, DateTime nowUtc)
    {
        if (string.IsNullOrEmpty(account)) return false;
        if (!_blocked.TryGetValue(account, out var entry)) return false;
        if (entry.ExpiresUtc > nowUtc) return true;
        _blocked.TryRemove(account, out _);
        return false;
    }

    public static string ReasonFor(string account)
        => _blocked.TryGetValue(account, out var e) ? e.Reason : "";

    // Wordt aangeroepen ná ForwardJsonAsync met de reply. Alleen als de reply zelf
    // "GEWEIGERD" heet én een limit-marker draagt slaat het account op slot.
    public static void RegisterIfLimitMarker(string account, string reply, DateTime nowUtc)
    {
        if (string.IsNullOrEmpty(account) || string.IsNullOrEmpty(reply)) return;
        var r = reply.ToLowerInvariant();
        var hit = LimitMarkers.FirstOrDefault(m => r.Contains(m));
        if (hit is null) return;
        _blocked[account] = (NextSessionRollUtc(nowUtc), hit);
    }

    // Voor tests / debugging.
    public static void Reset() => _blocked.Clear();
    public static int Count => _blocked.Count;
}

public static class Audit
{
    public static async Task AppendAsync(string storePath, string kind, string body, string result, string account = "")
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
}

// Tier-matrix uit CARDS.md. Volgorde telt: "ACCOUNT HALT" moet vóór "ACCOUNT
// STARTED"-achtige checks, en "LIMIT EXPIRED" vóór "LIMIT". Onbekende titel =>
// tier B (generieke kaart), want een bericht mag nooit stil verdwijnen.
public static class CardTier
{
    static readonly (string Needle, char Tier)[] Table =
    {
        ("CONFIG",         'B'),   // 1x per sessie-start — administratief maar leesbaar als kaart
        ("ACCOUNT STARTED",'C'),
        ("LIMIT EXPIRED",  'B'),   // per niet-gevulde limit — de reden dat een setup niets werd
        ("SIGNAL BLOCKED", 'C'),   // poort in BlockedGate promoveert de terminale melding naar B
        ("AUTO FLAT",      'B'),   // 1x per dag — het einde van de sessie is een moment
        ("ACCOUNT HALT",   'A'),
        ("EXIT",           'A'),
        ("PASSED",         'A'),
        ("FAILED",         'A'),
        ("PAYOUT",         'A'),
        ("FILL",           'B'),
        ("RISK OFF",       'B'),
        ("TRAIL",          'B'),
        ("DAY HALT",       'B'),
        ("DERISK",         'B'),
        ("LOCK",           'B'),
        ("THRESHOLD",      'B'),
        ("REGIME",         'B'),
        ("LIMIT",          'B'),
        ("MARKET",         'B'),
    };

    static readonly List<(string Needle, char Tier)> Overrides = new();

    // MEX_CARD_TIER_OVERRIDES="AUTO FLAT=B,EXIT=C" — tier is data, geen code.
    public static void LoadOverrides(string spec)
    {
        Overrides.Clear();
        foreach (var part in spec.Split(',', StringSplitOptions.RemoveEmptyEntries))
        {
            var kv = part.Split('=', 2);
            if (kv.Length == 2 && kv[1].Trim().Length == 1)
                Overrides.Add((kv[0].Trim().ToUpperInvariant(), char.ToUpperInvariant(kv[1].Trim()[0])));
        }
    }

    public static char For(string title)
    {
        var t = title.ToUpperInvariant();
        foreach (var (needle, tier) in Overrides)
            if (t.Contains(needle)) return tier;
        foreach (var (needle, tier) in Table)
            if (t.Contains(needle)) return tier;
        return 'B';
    }

    // Een expliciete override wint van alles — ook van de blocked-poort hieronder,
    // zodat "SIGNAL BLOCKED=B" in .env alsnog élke blokkade als kaart doorlaat.
    public static bool HasOverride(string title)
    {
        var t = title.ToUpperInvariant();
        foreach (var (needle, _) in Overrides)
            if (t.Contains(needle)) return true;
        return false;
    }
}

// D-28 uitbreiding 2 + 6 — waar gaat deze notificatie heen.
// Spiegelt `middleware/app/notify_routing.py` regel voor regel: dezelfde env-namen,
// dezelfde prioriteit (per-firm > per-fase > globaal). Bewust GEEN tweede routing-tabel:
// verandert de Python-kant, dan verandert deze mee — en andersom.
// Niets gezet => lege string => de aanroeper valt terug op MEX_DISCORD_WEBHOOK, dus een
// bestaande installatie zonder deze vars gedraagt zich exact als voorheen.
public static class NotifyRoute
{
    // "PA..." = funded, "APEX.../AP..." = eval, rest = other (geen fase-kandidaat).
    static string Phase(string account)
    {
        var a = (account ?? "").ToUpperInvariant().Trim();
        if (a.StartsWith("PA", StringComparison.Ordinal)) return "FUNDED";
        if (a.StartsWith("APEX", StringComparison.Ordinal) || a.StartsWith("AP", StringComparison.Ordinal)) return "EVAL";
        return "OTHER";
    }

    static string Firm(string account)
    {
        var a = (account ?? "").ToUpperInvariant().Trim();
        if (a.Contains("APEX")) return "APEX";
        if (a.Contains("FTMO")) return "FTMO";
        if (a.Contains("MFF") || a.Contains("MYFOREXFUNDS")) return "MFF";
        return "";
    }

    static string Env(params string[] names)
    {
        foreach (var name in names)
        {
            var v = (Environment.GetEnvironmentVariable(name) ?? "").Trim();
            if (v.Length > 0) return v;
        }
        return "";
    }

    /// kind: "trade" | "failure" · channel: "discord" | "telegram".
    /// Lege string = niets geconfigureerd; de aanroeper beslist wat dan.
    public static string WebhookFor(string account, string kind, string channel)
    {
        if (kind == "failure")
            return channel == "telegram"
                ? Env("TELEGRAM_ALERT_WEBHOOK", "ALERT_WEBHOOK")
                : Env("ALERT_WEBHOOK");

        var firm = Firm(account);
        var phase = Phase(account);
        var prefix = channel == "telegram" ? "TELEGRAM_NOTIFY_WEBHOOK" : "NOTIFY_WEBHOOK";

        var names = new List<string>();
        if (firm.Length > 0) names.Add(prefix + "_" + firm);
        if (phase != "OTHER") names.Add(prefix + "_" + phase);
        names.Add(prefix);
        if (channel == "telegram") names.Add("NOTIFY_WEBHOOK");   // cross-channel fallback
        return Env(names.ToArray());
    }

    /// Account uit een Pine-bericht — zelfde vorm die render-signal.js herkent
    /// (`^[A-Z]{2}\d{3}-`, bv. "PA016-0k-260813"), zodat er één conventie is.
    ///
    /// Let op: lang niet elke kaart draagt een account. FILL, EXIT, DERISK, PA DERISK en
    /// ACCOUNT STARTED zetten `jrnlAcct` vooraan; entries en RISK OFF dragen het in de
    /// eval-tail ("📍 PA016-0k-260813 | →🎯 …") en dan alleen als de eval loopt. DAY HALT,
    /// LIMIT EXPIRED, AUTO FLAT, ACCOUNT HALT, SIGNAL BLOCKED, CONFIG, PAYOUT en
    /// PASSED/FAILED dragen er géén — daar staat een reden of een prijs waar het account
    /// zou staan. Zonder herkend account: lege string, en de routing valt terug op de
    /// globale webhook. Nooit een zin als account behandelen: "PA Daily Loss Limit" uit
    /// een DAY HALT begint met "PA" en zou anders als funded gelezen worden.
    public static string AccountFrom(JsonObject obj)
    {
        var desc = obj["embeds"]?[0]?["description"]?.ToString() ?? "";
        // De eval-tail komt als LETTERLIJKE \n binnen (Pine schrijft "\\n"); render-signal.js
        // normaliseert dat ook voor het parsen. Zonder deze stap plakt het account aan de
        // vorige kolom en wordt het niet herkend.
        desc = desc.Replace("\\n", "\n");
        foreach (var part in desc.Split('|', '\n'))
        {
            var s = Trimmed(part);
            if (LooksLikeAccount(s)) return s;
        }
        return "";
    }

    // Voorloop-emoji en spaties eraf; de eval-tail begint met "📍 ".
    static string Trimmed(string part)
    {
        var s = (part ?? "").Trim();
        var i = 0;
        while (i < s.Length && !char.IsLetterOrDigit(s[i])) i++;
        s = s.Substring(i).Trim();
        var end = s.Length;
        while (end > 0 && char.IsWhiteSpace(s[end - 1])) end--;
        return s.Substring(0, end);
    }

    // Twee letters, drie cijfers, koppelteken — "PA016-0k-260813".
    static bool LooksLikeAccount(string s)
    {
        if (s.Length < 6 || s.Length > 40) return false;
        if (!char.IsLetter(s[0]) || !char.IsLetter(s[1])) return false;
        if (!char.IsDigit(s[2]) || !char.IsDigit(s[3]) || !char.IsDigit(s[4])) return false;
        return s[5] == '-';
    }
}

// D-28 uitbreiding 5 — rate-limit op kaarten.
// Elke kaart is een Chromium-render plus een webhook-post; Discord staat 30 berichten
// per minuut per webhook toe. Bij een burst gaan de kaarten dicht en volgt één korte
// samenvatting. Tier A gaat ALTIJD door: dat is het "er is iets heel erg mis"-signaal.
public static class PostRate
{
    static readonly int MaxPerMinute = int.TryParse(
        Environment.GetEnvironmentVariable("MEX_CARD_MAX_PER_MINUTE"), out var m) ? m : 12;

    static readonly object Gate = new object();
    static readonly Dictionary<string, List<DateTime>> Stamps = new Dictionary<string, List<DateTime>>();
    static readonly Dictionary<string, int> Suppressed = new Dictionary<string, int>();

    /// True = versturen. False = gedempt; `suppressed` telt hoeveel er sinds de laatste
    /// doorgelaten post zijn ingeslikt, zodat de volgende melding dat kan noemen.
    public static bool Allow(string webhook, char tier, out int suppressed)
    {
        suppressed = 0;
        if (tier == 'A') return true;                       // nooit dempen
        var key = webhook ?? "";
        var now = DateTime.UtcNow;
        lock (Gate)
        {
            List<DateTime> list;
            if (!Stamps.TryGetValue(key, out list)) { list = new List<DateTime>(); Stamps[key] = list; }
            list.RemoveAll(t => (now - t).TotalSeconds >= 60);
            if (list.Count >= MaxPerMinute)
            {
                int n;
                Suppressed.TryGetValue(key, out n);
                Suppressed[key] = n + 1;
                return false;
            }
            list.Add(now);
            Suppressed.TryGetValue(key, out suppressed);
            Suppressed.Remove(key);
            return true;
        }
    }
}

// Poort voor SIGNAL BLOCKED. Zonder poort is dit het luidruchtigste event dat er is:
// zodra een account op halt staat wordt élk geldig setup-signaal geblokkeerd, dus komt
// hetzelfde bericht bar na bar terug. De enige blokkade die nieuws is, is er één die de
// handelsdag (day halt) of het account (breach / eval passed) beëindigt — en die is één
// kaart waard, niet twintig. De rest wordt gedempt; het journaal houdt alles.
public static class BlockedGate
{
    // Markers uit f_persistentBlockers() in de Pine-scripts. De categorie is de
    // dedupe-sleutel, zodat "Day halt: PA Daily Loss Limit" en "Day halt: Day-cap"
    // samen één melding per dag opleveren.
    static readonly (string Needle, string Category)[] Terminal =
    {
        ("DAY HALT",    "day"),       // day-cap, daily loss, equity lock: klaar voor vandaag
        ("ACCOUNT:",    "account"),   // trailing breach / eval passed: klaar, punt
        ("BREACH",      "account"),
        ("EVAL PASSED", "account"),
    };

    static readonly ConcurrentDictionary<string, byte> Sent = new();

    public static bool Applies(string title) =>
        title.ToUpperInvariant().Contains("SIGNAL BLOCKED");

    /// True als dit de EERSTE terminale blokkade van deze handelsdag is (voor dit
    /// symbool). Routineblokkades en herhalingen geven false — die gaan niet door.
    public static bool Admit(string title, string description)
    {
        var text = description.ToUpperInvariant();
        var category = "";
        foreach (var (needle, cat) in Terminal)
            if (text.Contains(needle)) { category = cat; break; }
        if (category.Length == 0) return false;      // routineblokkade: ruis

        var key = TradingDay() + "|" + Symbol(title) + "|" + category;
        return Sent.TryAdd(key, 0);
    }

    // Handelsdag = kalenderdatum in New York, dezelfde grens als de dagteller in de
    // scripts (risk.trading_day). Valt de tijdzonedatabase weg, dan UTC — dan is de
    // demping hooguit een paar uur scheef, nooit stuk.
    static string TradingDay()
    {
        try
        {
            var et = TimeZoneInfo.FindSystemTimeZoneById("America/New_York");
            return TimeZoneInfo.ConvertTimeFromUtc(DateTime.UtcNow, et).ToString("yyyy-MM-dd");
        }
        catch (TimeZoneNotFoundException) { return DateTime.UtcNow.ToString("yyyy-MM-dd"); }
        catch (InvalidTimeZoneException) { return DateTime.UtcNow.ToString("yyyy-MM-dd"); }
    }

    // "⛔ MGC1! SIGNAL BLOCKED" -> "MGC1!". Het blocked-bericht draagt géén account-id,
    // dus het symbool is het fijnste wat we hebben om op te sleutelen.
    static string Symbol(string title)
    {
        foreach (var token in title.Split(' ', StringSplitOptions.RemoveEmptyEntries))
        {
            if (token.EndsWith("!", StringComparison.Ordinal)) return token.ToUpperInvariant();
            foreach (var ch in token)
                if (char.IsDigit(ch)) return token.ToUpperInvariant();
        }
        return "?";
    }
}

// Rendert een Discord-bericht tot PNG (Playwright/Chromium via render-signal.js)
// en post die als bijlage. Faalt er iets, dan gaat het originele tekstbericht
// alsnog door — een alert raken we nooit kwijt aan een render-probleem.
public static class CardRender
{
    public static string Node = "node";
    public static string Script = "";
    public static string OutDir = "/tmp/mex-cards";
    public static int TimeoutMs = 30000;
    public static bool Keep;

    // Chromium is zwaar; twee tegelijk is genoeg voor de alert-frequentie.
    static readonly SemaphoreSlim Gate = new(2, 2);

    public static async Task RenderAndPostAsync(HttpClient http, string url, string body,
                                                string title, string storePath, bool dryRun)
    {
        var outPath = Path.Combine(OutDir, $"card_{DateTime.UtcNow:yyyyMMdd-HHmmss}_{Guid.NewGuid():N}.png");
        string result;
        try
        {
            var (ok, err) = await RenderAsync(body, outPath);
            if (!ok)
            {
                var fb = await PostJsonAsync(http, url, body, dryRun);
                result = $"card failed ({err}) -> tekst-fallback: {fb}";
            }
            else if (dryRun)
            {
                result = $"dry_run -> kaart op {outPath}";
            }
            else
            {
                result = await PostCardAsync(http, url, body, outPath);
                if (result.StartsWith("error"))
                    result += " -> tekst-fallback: " + await PostJsonAsync(http, url, body, false);
            }
        }
        catch (Exception ex)
        {
            result = $"card exception {ex.GetType().Name}: {ex.Message}";
        }
        finally
        {
            if (!Keep && !dryRun) { try { File.Delete(outPath); } catch { /* best effort */ } }
        }
        await Audit.AppendAsync(storePath, "discord-card", title, result);
    }

    static async Task<(bool ok, string err)> RenderAsync(string payloadJson, string outPath)
    {
        await Gate.WaitAsync();
        try
        {
            var psi = new ProcessStartInfo(Node, $"\"{Script}\"")
            {
                WorkingDirectory = Path.GetDirectoryName(Script) is { Length: > 0 } dir ? dir : ".",
                RedirectStandardOutput = true,
                RedirectStandardError = true,
                UseShellExecute = false,
            };
            // Contract van render-signal.js: payload in MEX_SIGNAL_JSON, PNG naar MEX_SIGNAL_OUT.
            psi.Environment["MEX_SIGNAL_JSON"] = payloadJson;
            psi.Environment["MEX_SIGNAL_OUT"] = outPath;

            using var proc = Process.Start(psi);
            if (proc is null) return (false, "node start mislukt");
            var stderr = proc.StandardError.ReadToEndAsync();
            _ = proc.StandardOutput.ReadToEndAsync();

            using var cts = new CancellationTokenSource(TimeoutMs);
            try { await proc.WaitForExitAsync(cts.Token); }
            catch (OperationCanceledException)
            {
                try { proc.Kill(true); } catch { /* al weg */ }
                return (false, $"timeout na {TimeoutMs}ms");
            }

            if (proc.ExitCode != 0)
            {
                var e = (await stderr).Trim();
                return (false, $"exit {proc.ExitCode}: {(e.Length > 200 ? e[..200] : e)}");
            }
            return File.Exists(outPath) ? (true, "") : (false, "geen PNG geschreven");
        }
        finally { Gate.Release(); }
    }

    // De kaart vervangt de embed; username/avatar/content (role-ping) blijven staan.
    static async Task<string> PostCardAsync(HttpClient http, string url, string body, string outPath)
    {
        if (string.IsNullOrEmpty(url)) return "error: discord-url niet geconfigureerd";

        var src = JsonNode.Parse(body) as JsonObject;
        var payload = new JsonObject();
        foreach (var key in new[] { "username", "avatar_url", "content" })
            if (src?[key]?.ToString() is { Length: > 0 } v) payload[key] = v;

        for (var attempt = 1; attempt <= 3; attempt++)
        {
            try
            {
                using var form = new MultipartFormDataContent();
                form.Add(new StringContent(payload.ToJsonString(), Encoding.UTF8, "application/json"), "payload_json");
                var file = new ByteArrayContent(await File.ReadAllBytesAsync(outPath));
                file.Headers.ContentType = new MediaTypeHeaderValue("image/png");
                form.Add(file, "files[0]", "card.png");

                var resp = await http.PostAsync(url, form);
                var code = (int)resp.StatusCode;
                if (code < 400) return $"card sent {code} (poging {attempt})";
                if (code == 429) { await Task.Delay(2000); continue; }   // Discord rate limit
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

    static async Task<string> PostJsonAsync(HttpClient http, string url, string json, bool dryRun)
    {
        if (dryRun) return $"dry_run -> {(string.IsNullOrEmpty(url) ? "(geen url)" : url)}";
        if (string.IsNullOrEmpty(url)) return "error: discord-url niet geconfigureerd";
        try
        {
            using var content = new StringContent(json, Encoding.UTF8, "application/json");
            var resp = await http.PostAsync(url, content);
            return $"sent {(int)resp.StatusCode}";
        }
        catch (Exception ex) { return $"error {ex.GetType().Name}"; }
    }
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
