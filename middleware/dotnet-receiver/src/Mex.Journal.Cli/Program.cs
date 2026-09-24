using Mex.Journal.Adapters;
using Mex.Journal.Models;
using Mex.Journal.Recon;
using Mex.Journal;
using Mex.Journal.Sync;

// subcommand: sync --journal <journal.csv-map of --data exportmap> --sync-config <json>
if (args.Length > 1 && args[0] == "backfill")
{
    var bs = new NotionSync(NotionSyncConfig.Load(args[1]));
    var n = await bs.BackfillWebhookIdsAsync(Console.Out);
    Console.WriteLine($"backfill klaar: {n} rijen voorzien van Webhook ID");
    return 0;
}
if (args.Length > 0 && args[0] == "sync")
{
    string? dataDir = null, syncCfgPath = null;
    for (int i = 1; i < args.Length - 1; i++)
        switch (args[i]) { case "--data": dataDir = args[++i]; break; case "--sync-config": syncCfgPath = args[++i]; break; }
    if (dataDir == null || syncCfgPath == null)
    { Console.Error.WriteLine("gebruik: sync --data <exportmap> --sync-config <json>"); return 1; }
    var syncAdapter = new TradovateAdapter();
    var syncTrades = syncAdapter.Read(dataDir).ToList();
    Console.WriteLine($"{syncTrades.Count} trades ingelezen; sync starten...");
    var ns = new NotionSync(NotionSyncConfig.Load(syncCfgPath));
    await ns.ResolveRelationsAsync(Console.Out);
    var (c, u, f) = await ns.SyncAsync(syncTrades, Console.Out);
    Console.WriteLine($"sync klaar: {c} nieuw, {u} bijgewerkt, {f} mislukt");
    return f > 0 ? 3 : 0;
}

// mexjournal --data <exportmap> [--alerts <alertlog.csv>] --out <uitvoermap>
string? data = null, alertsPath = null, outDir = "out"; string? configPath = null;
for (int i = 0; i < args.Length - 1; i++)
    switch (args[i]) { case "--data": data = args[++i]; break;
        case "--alerts": alertsPath = args[++i]; break; case "--out": outDir = args[++i]; break;
        case "--config": configPath = args[++i]; break; }
if (data == null) { Console.Error.WriteLine("gebruik: --data <map> [--alerts <csv>] --out <map>"); return 1; }
Directory.CreateDirectory(outDir);

var adapter = new TradovateAdapter();
if (!adapter.CanHandle(data)) { Console.Error.WriteLine($"geen *_Fills.csv gevonden in {data}"); return 1; }
var trades = adapter.Read(data).ToList();

// journal.csv volgens contract
var journalPath = Path.Combine(outDir, "journal.csv");
File.WriteAllLines(journalPath,
    new[] { string.Join(",", TradeRecord.Columns) }.Concat(trades.Select(t => t.ToCsvRow())));

// fill-tijden per account voor recon (uit de fills zelf, via adapter opnieuw lezen is dubbel — afleiden uit trades kan niet 1:1, dus lees fills licht)
var fillTimes = new Dictionary<string, List<DateTime>>();
foreach (var f in Directory.EnumerateFiles(data, "*_Fills.csv"))
{
    var acc = TradovateAdapter.ExtractAccount(f);
    var times = Csv.ReadFile(f)
        .Select(r => DateTime.TryParse(r.GetValueOrDefault("_timestamp", ""),
            System.Globalization.CultureInfo.InvariantCulture,
            System.Globalization.DateTimeStyles.AdjustToUniversal |
            System.Globalization.DateTimeStyles.AssumeUniversal, out var t) ? t : (DateTime?)null)
        .Where(t => t.HasValue).Select(t => t!.Value).ToList();
    fillTimes[acc] = times;
}

var fleetCfg = FleetConfig.Load(configPath);
var missing = fleetCfg.ExpectedAccounts.Where(a => !fillTimes.ContainsKey(a)).ToList();
var unexpected = fleetCfg.ExpectedAccounts.Count > 0
    ? fillTimes.Keys.Where(a => !fleetCfg.ExpectedAccounts.Contains(a)).ToList() : new List<string>();
ReconResult? recon = null;
List<AlertEvent> alerts = new();
if (alertsPath != null && File.Exists(alertsPath))
{
    alerts = TvAlertLogAdapter.Read(alertsPath);
    recon = ReconciliationEngine.Run(alerts, trades, fillTimes, TimeSpan.FromMinutes(3));
}

// rapport
var rep = new System.Text.StringBuilder();
rep.AppendLine("# MEX Journal — ingest & reconciliatie");
rep.AppendLine($"\nGegenereerd: {DateTime.UtcNow:yyyy-MM-dd HH:mm} UTC\n");
rep.AppendLine($"## Journal\n");
rep.AppendLine($"- Trades (pairings): **{trades.Count}** over {trades.Select(t => t.Account).Distinct().Count()} accounts");
rep.AppendLine($"- Netto P&L: **${trades.Sum(t => t.NetPnl):N2}** (bruto ${trades.Sum(t => t.GrossPnl):N2}, fees ${trades.Sum(t => t.Fees):N2})");
foreach (var g in trades.GroupBy(t => t.Account).OrderBy(g => g.Key))
    rep.AppendLine($"  - {g.Key[^5..]}: {g.Count()} pairings, net ${g.Sum(t => t.NetPnl):N2}, " +
        $"exit-reasons: {string.Join(", ", g.GroupBy(t => t.ExitReason == "" ? "?" : t.ExitReason).OrderByDescending(x => x.Count()).Select(x => $"{x.Key}×{x.Count()}"))}, " +
        $"interventies: {g.Count(t => t.Intervention != "None")}");
rep.AppendLine($"- Geplande SL bekend: {trades.Count(t => t.PlannedSlPx.HasValue)}/{trades.Count} · R-multiple berekend: {trades.Count(t => t.RMultiple.HasValue)}/{trades.Count}");
if (recon != null)
{
    rep.AppendLine($"\n## Reconciliatie (alerts ↔ fills, ±3 min)\n");
    rep.AppendLine($"- Alerts totaal: {recon.TotalAlerts}, delivery-fouten: {recon.FailedDeliveries}");
    foreach (var (k, v) in recon.DeliveryFailures.OrderByDescending(kv => kv.Value))
        rep.AppendLine($"  - {v}× {k}");
    rep.AppendLine($"- FILL-alerts: {recon.FillAlerts}, gematcht met broker-fill: {recon.MatchedFillAlerts}, " +
        $"**zonder match: {recon.UnmatchedFillAlerts.Count}**");
    foreach (var u in recon.UnmatchedFillAlerts.Take(10))
        rep.AppendLine($"  - ! {u.TimeUtc:MM-dd HH:mm} {u.Account} {u.Ticker} {u.Title}");
    rep.AppendLine($"- Accounts met fills maar zonder fill-alerts: {string.Join(", ", recon.AccountsWithoutAlerts.Select(a => a[^5..]))}");
    rep.AppendLine($"\n### Geblokkeerde signalen per reden");
    foreach (var (k, v) in recon.BlockedByReason.OrderByDescending(kv => kv.Value))
        rep.AppendLine($"- {v}× {k}");
}
if (fleetCfg.ExpectedAccounts.Count > 0)
{
    rep.AppendLine($"\n## Compleetheid ({fleetCfg.ExpectedAccounts.Count} verwachte accounts)\n");
    if (missing.Count == 0) rep.AppendLine("- \u2705 Alle verwachte accounts aangeleverd");
    else foreach (var m in missing) rep.AppendLine($"- \ud83d\udea8 **ONTBREEKT: {m}** \u2014 geen exports gevonden");
    foreach (var u in unexpected) rep.AppendLine($"- \u26a0\ufe0f Onverwacht account in data: {u}");
}
var reportPath = Path.Combine(outDir, "recon_report.md");
File.WriteAllText(reportPath, rep.ToString());

Console.WriteLine($"journal:  {journalPath}  ({trades.Count} records)");
Console.WriteLine($"rapport:  {reportPath}");
Console.WriteLine($"net P&L:  ${trades.Sum(t => t.NetPnl):N2}");
var digestTitle = missing.Count > 0 ? "\ud83d\udea8 MEX Journal \u2014 accounts ONTBREKEN" : "\ud83d\udcd2 MEX Journal \u2014 dagelijkse ingest";
var digest = $"**{trades.Count}** trades \u00b7 netto **${trades.Sum(t => t.NetPnl):N2}**" +
    (recon != null ? $"\nFill-alerts gematcht: {recon.MatchedFillAlerts}/{recon.FillAlerts} \u00b7 delivery-fouten: {recon.FailedDeliveries}" : "") +
    (missing.Count > 0 ? $"\n\ud83d\udea8 Ontbrekend: {string.Join(", ", missing.Select(m => m[^5..]))}" : "\n\u2705 Compleetheid OK");
var posted = await DiscordNotifier.PostAsync(fleetCfg.DiscordWebhookEnvVar ?? "MEX_DISCORD_WEBHOOK", digestTitle, digest, missing.Count > 0 ? 15158332 : 3066993);
Console.WriteLine($"discord:  {(posted ? "verzonden" : "overgeslagen (geen webhook env-var)")}");
return missing.Count > 0 ? 2 : 0;
