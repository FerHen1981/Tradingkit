using System.Net.Http.Headers;
using System.Net.Http.Json;
using System.Text.Json;
using System.Text.Json.Nodes;
using Mex.Journal.Models;

namespace Mex.Journal.Sync;

/// <summary>Schrijft TradeRecords idempotent naar de Notion Trade Journal (MEX TRADERS HQ).
/// Idempotency: "Webhook ID" = trade_id (update i.p.v. dupliceren). Relaties worden bij start
/// op naam geresolved en per trade meegeschreven. Token via env-var (secret buiten repo).</summary>
public class NotionSyncConfig
{
    public string TokenEnvVar { get; set; } = "MEX_NOTION_TOKEN";
    public string NotionVersion { get; set; } = "2022-06-28";
    public string JournalDatabaseId { get; set; } = "";
    public string FrameworkDatabaseId { get; set; } = "";
    public string AccountsDatabaseId { get; set; } = "";
    public string AssetsDatabaseId { get; set; } = "";
    public string ProviderPageId { get; set; } = "";
    public string AccountTypesDatabaseId { get; set; } = "";
    public string RiskProfileDatabaseId { get; set; } = "";
    public Dictionary<string, string> ContractToRiskProfile { get; set; } = new();
    public Dictionary<string, string> AccountTypeOverride { get; set; } = new();
    public string RecapDatabaseId { get; set; } = "";
    public string RecapTitlePrefix { get; set; } = "";
    public Dictionary<string, string> ContractToFramework { get; set; } = new();
    public Dictionary<string, string> ContractToAsset { get; set; } = new();
    public int ThrottleMs { get; set; } = 350;

    public static NotionSyncConfig Load(string path) =>
        JsonSerializer.Deserialize<NotionSyncConfig>(File.ReadAllText(path))
        ?? throw new InvalidOperationException("sync-config onleesbaar");
}

public class NotionSync
{
    readonly NotionSyncConfig _cfg;
    readonly HttpClient _http;
    readonly Dictionary<string, string> _frameworkIds = new();
    readonly Dictionary<string, string> _accountIds = new();
    readonly Dictionary<string, string> _assetIds = new();
    readonly Dictionary<string, string> _accountTypeIds = new();
    readonly Dictionary<string, string> _riskProfileIds = new();
    readonly Dictionary<string, string> _recapIds = new();
    readonly HashSet<string> _recapDated = new();
    readonly Dictionary<string, string> _titlePropCache = new();

    public NotionSync(NotionSyncConfig cfg)
    {
        _cfg = cfg;
        var token = Environment.GetEnvironmentVariable(cfg.TokenEnvVar)
            ?? throw new InvalidOperationException($"env-var {cfg.TokenEnvVar} niet gezet");
        _http = new HttpClient { BaseAddress = new Uri("https://api.notion.com/") };
        _http.DefaultRequestHeaders.Authorization = new AuthenticationHeaderValue("Bearer", token);
        _http.DefaultRequestHeaders.Add("Notion-Version", cfg.NotionVersion);
    }

    async Task<JsonNode?> PostAsync(string path, object body)
    {
        var resp = await _http.PostAsJsonAsync(path, body);
        var txt = await resp.Content.ReadAsStringAsync();
        if (!resp.IsSuccessStatusCode)
            throw new HttpRequestException($"{path} -> {(int)resp.StatusCode}: {txt[..Math.Min(300, txt.Length)]}");
        return JsonNode.Parse(txt);
    }

    async Task<List<(string id, string title)>> QueryAllTitles(string databaseId)
    {
        var results = new List<(string, string)>();
        string? cursor = null;
        do
        {
            object body = cursor == null ? new { page_size = 100 } : new { page_size = 100, start_cursor = cursor };
            var node = await PostAsync($"v1/databases/{databaseId}/query", body);
            foreach (var page in node!["results"]!.AsArray())
            {
                var id = page!["id"]!.GetValue<string>();
                string title = "";
                foreach (var prop in page["properties"]!.AsObject())
                    if (prop.Value?["type"]?.GetValue<string>() == "title")
                    {
                        var arr = prop.Value["title"]!.AsArray();
                        title = string.Join("", arr.Select(t => t?["plain_text"]?.GetValue<string>() ?? ""));
                        break;
                    }
                results.Add((id, title));
            }
            cursor = node["has_more"]!.GetValue<bool>() ? node["next_cursor"]?.GetValue<string>() : null;
            await Task.Delay(_cfg.ThrottleMs);
        } while (cursor != null);
        return results;
    }

    public async Task ResolveRelationsAsync(TextWriter log)
    {
        foreach (var (id, title) in await QueryAllTitles(_cfg.FrameworkDatabaseId))
            foreach (var frag in _cfg.ContractToFramework.Values.Distinct())
                if (title.Contains(frag, StringComparison.OrdinalIgnoreCase)) _frameworkIds[frag] = id;
        foreach (var (id, title) in await QueryAllTitles(_cfg.AccountsDatabaseId))
            _accountIds[title.Trim()] = id;
        foreach (var (id, title) in await QueryAllTitles(_cfg.AssetsDatabaseId))
            _assetIds[title.Trim()] = id;
        log.WriteLine($"resolved: {_frameworkIds.Count} frameworks, {_accountIds.Count} accounts, {_assetIds.Count} assets");
    }

    async Task<string> GetTitlePropNameAsync(string databaseId)
    {
        if (_titlePropCache.TryGetValue(databaseId, out var cached)) return cached;
        var resp = await _http.GetAsync($"v1/databases/{databaseId}");
        var txt = await resp.Content.ReadAsStringAsync();
        if (!resp.IsSuccessStatusCode) throw new HttpRequestException($"GET db {databaseId} -> {(int)resp.StatusCode}");
        var node = JsonNode.Parse(txt)!;
        foreach (var prop in node["properties"]!.AsObject())
            if (prop.Value?["type"]?.GetValue<string>() == "title")
            { _titlePropCache[databaseId] = prop.Key; return prop.Key; }
        throw new InvalidOperationException($"geen titelproperty in {databaseId}");
    }

    /// <summary>Zoekt op exacte titel; maakt aan als afwezig. Retourneert page_id.</summary>
    async Task<string> ResolveOrCreateAsync(string databaseId, Dictionary<string, string> cache, string name, TextWriter log)
    {
        if (cache.TryGetValue(name, out var hit)) return hit;
        var titleProp = await GetTitlePropNameAsync(databaseId);
        var q = new { filter = new { property = titleProp, title = new { equals = name } }, page_size = 1 };
        var node = await PostAsync($"v1/databases/{databaseId}/query", q);
        var arr = node!["results"]!.AsArray();
        string id;
        if (arr.Count > 0) id = arr[0]!["id"]!.GetValue<string>();
        else
        {
            var created = await PostAsync("v1/pages", new { parent = new { database_id = databaseId },
                properties = new Dictionary<string, object> { [titleProp] = Title(name) } });
            id = created!["id"]!.GetValue<string>();
            log.WriteLine($"  + aangemaakt in {databaseId[..8]}…: {name}");
        }
        cache[name] = id;
        await Task.Delay(_cfg.ThrottleMs);
        return id;
    }

    static string AccountTypeNameFor(string account, Dictionary<string, string> overrides)
    {
        if (overrides.TryGetValue(account, out var o)) return o;
        bool isPa = account.StartsWith("PAAPEX", StringComparison.OrdinalIgnoreCase);
        return isPa ? "Apex 50k PA (EOD)" : "Apex 50k Eval (Intraday)";
    }

    static (string label, int hour) SessionFor(DateTime entryUtc)
    {
        var et = entryUtc.AddHours(-4);
        var t = et.TimeOfDay;
        string label =
            t >= new TimeSpan(9,30,0) && t < new TimeSpan(10,30,0) ? "Initial Balance" :
            t >= new TimeSpan(10,30,0) && t < new TimeSpan(12,0,0) ? "New York AM" :
            t >= new TimeSpan(12,0,0) && t < new TimeSpan(17,0,0) ? "New York PM" :
            t >= new TimeSpan(2,0,0) && t < new TimeSpan(9,30,0) ? "London" : "Asia";
        return (label, et.Hour);
    }

    async Task<string?> FindExistingAsync(string tradeId)
    {
        var body = new { filter = new { property = "Webhook ID", rich_text = new { equals = tradeId } }, page_size = 1 };
        var node = await PostAsync($"v1/databases/{_cfg.JournalDatabaseId}/query", body);
        var arr = node!["results"]!.AsArray();
        return arr.Count > 0 ? arr[0]!["id"]!.GetValue<string>() : null;
    }

    static object Title(string s) => new { title = new[] { new { text = new { content = s } } } };
    static object Rich(string s) => new { rich_text = new[] { new { text = new { content = s } } } };
    static object Num(decimal? v) => new { number = v };
    static object Sel(string s) => new { select = new { name = s } };
    static object Rel(params string?[] ids) => new { relation = ids.Where(i => i != null).Select(i => new { id = i }).ToArray() };

    async Task<Dictionary<string, object>> BuildPropsAsync(TradeRecord t, TextWriter log)
    {
        var fwFrag = _cfg.ContractToFramework.GetValueOrDefault(t.Contract);
        var asName = _cfg.ContractToAsset.GetValueOrDefault(t.Contract);
        var props = new Dictionary<string, object>
        {
            ["Trade ID"] = Title(t.TradeId),
            ["Webhook ID"] = Rich(t.TradeId),
            ["Direction"] = Sel(t.Direction == "Long" ? "BUY" : "SELL"),
            ["Contract"] = Rich(t.Contract),
            ["PositionSize"] = Num(t.Qty),
            ["Open Date"] = new { date = t.EntryTimeUtc == null ? null : new { start = t.EntryTimeUtc.Value.AddHours(-4).ToString("yyyy-MM-ddTHH:mm:ss") } },
            ["Close Date"] = new { date = t.ExitTimeUtc == null ? null : new { start = t.ExitTimeUtc.Value.AddHours(-4).ToString("yyyy-MM-ddTHH:mm:ss") } },
            ["Entry Price ($)"] = Num(t.EntryPrice),
            ["Exit Price ($)"] = Num(t.ExitPrice),
            ["Gross PnL"] = Num(t.GrossPnl),
            ["Commissions"] = Num(t.Fees),
            // Session als tijdvak-label + uur-blok (24/dag), o.b.v. entry-ET
            ["Source"] = Sel("Tradovate CSV Import"),
            ["Sync Status"] = Sel("Auto"),
            ["Intervention"] = Sel(t.Intervention),
            ["Apex Trade Date"] = new { date = string.IsNullOrEmpty(t.ApexTradeDate) ? null : new { start = t.ApexTradeDate } },
            ["Notes"] = Rich($"acct={t.Account}" +
                (t.PlannedSlPx.HasValue ? $"; plannedSL={t.PlannedSlPx}" : "") +
                (t.PlannedTpPx.HasValue ? $"; plannedTP={t.PlannedTpPx}" : "")),
        };
        if (t.RMultiple.HasValue) props["R Multiple"] = Num(t.RMultiple);
        if (t.BuyFillId != "") props["Buy Fill ID"] = Rich(t.BuyFillId);
        if (t.SellFillId != "") props["Sell Fill ID"] = Rich(t.SellFillId);
        if (t.ResultTicks.HasValue) props["Result (Ticks)"] = Num(t.ResultTicks);
        if (t.DurationMin.HasValue) props["Duration (min)"] = Num(t.DurationMin);
        if (t.EntryTimeUtc.HasValue) props["Day"] = Sel(t.EntryTimeUtc.Value.AddHours(-4).DayOfWeek.ToString());
        props["Strategy"] = Sel("MEX PROP TRADER v6.4.4j");
        var status = t.ExitReason switch
        { "SL" => "Closed by S/L", "TP" => "Closed by T/P", "Manual" => "Closed Manually", "Flat" => "Flattened (EOD)", _ => null };
        if (status != null) props["Status"] = Sel(status);
        if (t.EntryTimeUtc.HasValue)
        {
            var (sessLabel, hour) = SessionFor(t.EntryTimeUtc.Value);
            props["Session"] = Sel(sessLabel);
            props["Hour (ET)"] = Num(hour);
        }
        if (fwFrag != null && _frameworkIds.TryGetValue(fwFrag, out var fwId)) props["Framework"] = Rel(fwId);

        // Account: resolve-or-create (evals krijgen zo ook hun relatie)
        string accId = _accountIds.TryGetValue(t.Account, out var accHit) ? accHit
            : await ResolveOrCreateAsync(_cfg.AccountsDatabaseId, _accountIds, t.Account, log);
        props["Account"] = Rel(accId);

        // Assets: frontmonth-notatie, resolve-or-create
        if (asName != null)
        {
            string asId = _assetIds.TryGetValue(asName, out var asHit) ? asHit
                : await ResolveOrCreateAsync(_cfg.AssetsDatabaseId, _assetIds, asName, log);
            props["Assets"] = Rel(asId);
        }

        // Account Types: naamconventie [Provider][Size][PA/EVAL]([DD-type]), resolve-or-create
        if (!string.IsNullOrEmpty(_cfg.AccountTypesDatabaseId))
        {
            var typeName = AccountTypeNameFor(t.Account, _cfg.AccountTypeOverride);
            var typeId = await ResolveOrCreateAsync(_cfg.AccountTypesDatabaseId, _accountTypeIds, typeName, log);
            props["Account Types"] = Rel(typeId);
        }

        // Risk Profile: genormaliseerd per strategie (config-map per contract)
        if (!string.IsNullOrEmpty(_cfg.RiskProfileDatabaseId)
            && _cfg.ContractToRiskProfile.TryGetValue(t.Contract, out var rpName))
        {
            var rpId = await ResolveOrCreateAsync(_cfg.RiskProfileDatabaseId, _riskProfileIds, rpName, log);
            props["Risk Profile"] = Rel(rpId);
        }

        if (!string.IsNullOrEmpty(_cfg.ProviderPageId)) props["Provider Account"] = Rel(_cfg.ProviderPageId);

        // Recap: één dagpagina per Apex-handelsdag, trades eraan gekoppeld
        if (!string.IsNullOrEmpty(_cfg.RecapDatabaseId) && !string.IsNullOrEmpty(t.ApexTradeDate))
        {
            var recapName = _cfg.RecapTitlePrefix + t.ApexTradeDate;
            var recapId = await ResolveOrCreateAsync(_cfg.RecapDatabaseId, _recapIds, recapName, log);
            if (_recapDated.Add(recapId))
            {
                await _http.PatchAsync($"v1/pages/{recapId}", JsonContent.Create(new { properties =
                    new Dictionary<string, object> { ["Date"] = new { date = new { start = t.ApexTradeDate } } } }));
                await Task.Delay(_cfg.ThrottleMs);
            }
            props["Recap"] = Rel(recapId);
        }
        return props;
    }


    /// <summary>Eenmalig: zet Webhook ID = Trade ID op alle journal-rijen waar hij leeg is.</summary>
    public async Task<int> BackfillWebhookIdsAsync(TextWriter log)
    {
        int fixedCount = 0; string? cursor = null;
        do
        {
            object body = cursor == null ? new { page_size = 100 } : new { page_size = 100, start_cursor = cursor };
            var node = await PostAsync($"v1/databases/{_cfg.JournalDatabaseId}/query", body);
            foreach (var page in node!["results"]!.AsArray())
            {
                var id = page!["id"]!.GetValue<string>();
                var props = page["properties"]!;
                var wh = props["Webhook ID"]?["rich_text"]?.AsArray();
                if (wh != null && wh.Count > 0) continue;
                var titleArr = props["Trade ID"]?["title"]?.AsArray();
                var title = titleArr == null ? "" : string.Join("", titleArr.Select(t => t?["plain_text"]?.GetValue<string>() ?? ""));
                if (title == "") continue;
                var resp = await _http.PatchAsync($"v1/pages/{id}",
                    System.Net.Http.Json.JsonContent.Create(new { properties = new Dictionary<string, object> { ["Webhook ID"] = Rich(title) } }));
                if (resp.IsSuccessStatusCode) { fixedCount++; if (fixedCount % 50 == 0) log.WriteLine($"  {fixedCount}..."); }
                await Task.Delay(_cfg.ThrottleMs);
            }
            cursor = node["has_more"]!.GetValue<bool>() ? node["next_cursor"]?.GetValue<string>() : null;
        } while (cursor != null);
        return fixedCount;
    }

    public async Task<(int created, int updated, int failed)> SyncAsync(IEnumerable<TradeRecord> trades, TextWriter log)
    {
        int created = 0, updated = 0, failed = 0;
        foreach (var t in trades)
        {
            try
            {
                var existing = await FindExistingAsync(t.TradeId);
                await Task.Delay(_cfg.ThrottleMs);
                var props = await BuildPropsAsync(t, log);
                if (existing == null)
                {
                    await PostAsync("v1/pages", new { parent = new { database_id = _cfg.JournalDatabaseId }, properties = props });
                    created++;
                }
                else
                {
                    var resp = await _http.PatchAsync($"v1/pages/{existing}", JsonContent.Create(new { properties = props }));
                    if (!resp.IsSuccessStatusCode) throw new HttpRequestException(await resp.Content.ReadAsStringAsync());
                    updated++;
                }
                await Task.Delay(_cfg.ThrottleMs);
            }
            catch (Exception ex)
            {
                failed++;
                log.WriteLine($"FAIL {t.TradeId}: {ex.Message[..Math.Min(200, ex.Message.Length)]}");
            }
        }
        return (created, updated, failed);
    }
}
