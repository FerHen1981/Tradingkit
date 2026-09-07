using System.Globalization;
using Mex.Journal.Models;
namespace Mex.Journal.Adapters;

/// <summary>Leest Tradovate-exportdrietallen ({prefix}{ACCOUNT}_Orders/_Fills/_Performance.csv)
/// uit een map en bouwt canonieke TradeRecords: pairing van Performance, officiële Apex-tradedate
/// via fill→_tradeDate, commissie pro-rata per pairing, exit-reason + geplande SL/TP uit Orders,
/// interventie-detectie via Market-orders zonder 'multibracket'-tekst.</summary>
public class TradovateAdapter : ITradeSourceAdapter
{
    public string SourceName => "Tradovate";
    static readonly CultureInfo Inv = CultureInfo.InvariantCulture;

static readonly Dictionary<string, decimal> TickSize = new()
    { ["MGC"]=0.1m, ["GC"]=0.1m, ["ES"]=0.25m, ["MES"]=0.25m, ["NQ"]=0.25m, ["MNQ"]=0.25m };
    static readonly Dictionary<string, decimal> PointValue = new()
    { ["MGC"]=10m, ["GC"]=100m, ["ES"]=50m, ["MES"]=5m, ["NQ"]=20m, ["MNQ"]=2m };

    public bool CanHandle(string path) =>
        Directory.Exists(path) && Directory.EnumerateFiles(path, "*_Fills.csv").Any();

    public IReadOnlyList<TradeRecord> Read(string dir)
    {
        var records = new List<TradeRecord>();
        foreach (var fillsPath in Directory.EnumerateFiles(dir, "*_Fills.csv"))
        {
            var acc = ExtractAccount(fillsPath);
            var baseName = fillsPath[..^"_Fills.csv".Length];
            string? ordersPath = File.Exists(baseName + "_Orders.csv") ? baseName + "_Orders.csv" : null;
            string? perfPath = new[] { "_Performance.csv", "_P.csv", ".csv" }
                .Select(sfx => baseName + sfx).FirstOrDefault(File.Exists);
            if (perfPath == null) continue;

            var fills = ReadFills(fillsPath, acc);
            var orders = ordersPath != null ? ReadOrders(ordersPath, acc) : new List<BrokerOrder>();
            var pairs = ReadPairs(perfPath, acc);
            records.AddRange(Build(acc, fills, orders, pairs));
        }
        return records;
    }

    public static string ExtractAccount(string path)
    {
        var m = System.Text.RegularExpressions.Regex.Match(Path.GetFileName(path), @"([A-Z]*APEX\d+|PAAPEX\d+)");
        return m.Success ? m.Value : Path.GetFileNameWithoutExtension(path);
    }

    static DateTime? Et(string s) => DateTime.TryParseExact(s, "MM/dd/yyyy HH:mm:ss", Inv,
        DateTimeStyles.None, out var t) ? t : null;
    static DateTime EtToUtc(DateTime et) => et.AddHours(4); // ET zomer; datasetbreed geldig

    List<Fill> ReadFills(string path, string acc) => Csv.ReadFile(path).Select(r => new Fill(
        r.GetValueOrDefault("Fill ID",""), acc, r.GetValueOrDefault("Product",""),
        r.GetValueOrDefault("Contract",""), r.GetValueOrDefault("B/S","").Trim(),
        int.TryParse(r.GetValueOrDefault("filledQty",""), out var q) ? q :
            int.TryParse(r.GetValueOrDefault("Quantity",""), out var q2) ? q2 : 0,
        Csv.Money(r.GetValueOrDefault("avgPrice", r.GetValueOrDefault("Price",""))),
        DateTime.TryParse(r.GetValueOrDefault("_timestamp",""), Inv,
            DateTimeStyles.AdjustToUniversal | DateTimeStyles.AssumeUniversal, out var ts)
            ? ts : EtToUtc(Et(r.GetValueOrDefault("Timestamp","")) ?? default),
        r.GetValueOrDefault("_tradeDate",""),
        Csv.Money(r.GetValueOrDefault("commission","")))).ToList();

    List<BrokerOrder> ReadOrders(string path, string acc) => Csv.ReadFile(path).Select(r => new BrokerOrder(
        r.GetValueOrDefault("id", r.GetValueOrDefault("Order ID","")), acc,
        r.GetValueOrDefault("Product",""), r.GetValueOrDefault("Contract",""),
        r.GetValueOrDefault("B/S","").Trim(), r.GetValueOrDefault("Type","").Trim(),
        r.GetValueOrDefault("Status","").Trim(),
        int.TryParse(r.GetValueOrDefault("Quantity",""), out var q) ? q : 0,
        NullableMoney(r.GetValueOrDefault("Limit Price","")), NullableMoney(r.GetValueOrDefault("Stop Price","")),
        NullableMoney(r.GetValueOrDefault("Avg Fill Price","")),
        Et(r.GetValueOrDefault("Timestamp","")), Et(r.GetValueOrDefault("Fill Time","")),
        r.GetValueOrDefault("Text","").Trim())).ToList();

    static decimal? NullableMoney(string s) => string.IsNullOrWhiteSpace(s) ? null : Csv.Money(s);

    List<PerfPair> ReadPairs(string path, string acc) => Csv.ReadFile(path).Select(r => new PerfPair(
        acc, Csv.Money(r.GetValueOrDefault("pnl","")),
        int.TryParse(r.GetValueOrDefault("qty",""), out var q) ? q : 1,
        r.GetValueOrDefault("buyFillId",""), r.GetValueOrDefault("sellFillId",""),
        Csv.Money(r.GetValueOrDefault("buyPrice","")), Csv.Money(r.GetValueOrDefault("sellPrice","")),
        Et(r.GetValueOrDefault("boughtTimestamp","")) ?? default,
        Et(r.GetValueOrDefault("soldTimestamp","")) ?? default)).ToList();

    IEnumerable<TradeRecord> Build(string acc, List<Fill> fills, List<BrokerOrder> orders, List<PerfPair> pairs)
    {
        var fillById = fills.Where(f => f.FillId != "").ToDictionary(f => f.FillId, f => f);
        // commissie pro-rata: fill-commissie verdeeld over pairings naar qty-aandeel
        var fillPairQty = new Dictionary<string, int>();
        foreach (var p in pairs)
            foreach (var id in new[] { p.BuyFillId, p.SellFillId })
                if (id != "") fillPairQty[id] = fillPairQty.GetValueOrDefault(id) + p.Qty;

        int seq = 0;
        foreach (var p in pairs.OrderBy(p => Math.Min(p.BoughtEt.Ticks, p.SoldEt.Ticks)))
        {
            seq++;
            fillById.TryGetValue(p.BuyFillId, out var bf);
            fillById.TryGetValue(p.SellFillId, out var sf);
            bool isLong = p.BoughtEt <= p.SoldEt; // entry = eerste poot
            var entryEt = isLong ? p.BoughtEt : p.SoldEt;
            var exitEt = isLong ? p.SoldEt : p.BoughtEt;
            var entryPx = isLong ? p.BoughtPx : p.SoldPx;
            var exitPx = isLong ? p.SoldPx : p.BoughtPx;
            var product = bf?.Product ?? sf?.Product ?? "";
            var exitFill = isLong ? sf : bf;
            var entryFill = isLong ? bf : sf;

            decimal fees = 0m;
            foreach (var (fill, id) in new[] { (bf, p.BuyFillId), (sf, p.SellFillId) })
                if (fill != null && fillPairQty.TryGetValue(id, out var tot) && tot > 0)
                    fees += fill.Commission * p.Qty / tot;

            var rec = new TradeRecord
            {
                TradeId = (p.BuyFillId != "" && p.SellFillId != "") ? $"{acc[^3..]}_{p.BuyFillId}_{p.SellFillId}" : $"{acc[^3..]}_{entryEt:yyyyMMdd_HHmmss}_{seq:000}",
                Account = acc, Instrument = product,
                Contract = bf?.Contract ?? sf?.Contract ?? "",
                Direction = isLong ? "Long" : "Short", Qty = p.Qty,
                EntryTimeUtc = EtToUtc(entryEt), ExitTimeUtc = EtToUtc(exitEt),
                EntryPrice = entryPx, ExitPrice = exitPx,
                GrossPnl = p.Pnl, Fees = Math.Round(fees, 2),
                ApexTradeDate = exitFill?.TradeDate ?? entryFill?.TradeDate ?? "",
                Session = SessionOf(entryEt),
                BuyFillId = p.BuyFillId, SellFillId = p.SellFillId,
                DurationMin = Math.Round((decimal)(exitEt - entryEt).TotalMinutes, 1),
            };

            // exit-reason via order-match op Fill Time + side
            var exitOrder = orders.FirstOrDefault(o => o.Status == "Filled" && o.FillTimeEt == exitEt
                && o.Side == (isLong ? "Sell" : "Buy"));
            rec.ExitReason = exitOrder == null ? "" : exitOrder.Type switch
            {
                "Stop" => "SL", "Limit" => "TP",
                "Market" when exitOrder.Text == "" => "Manual",
                "Market" => "Flat", _ => exitOrder.Type
            };
            if (exitOrder is { Type: "Market", Text: "" })
            { rec.Intervention = "Manual Close"; }

            // geplande brackets: tegenzijde-orders geplaatst binnen 90s rond entry
            var win = orders.Where(o => o.PlacedEt.HasValue
                && Math.Abs((o.PlacedEt.Value - entryEt).TotalSeconds) <= 90
                && o.Side == (isLong ? "Sell" : "Buy"));
            rec.PlannedSlPx = win.Where(o => o.Type == "Stop").Select(o => o.StopPrice).FirstOrDefault(v => v.HasValue);
            rec.PlannedTpPx = win.Where(o => o.Type == "Limit").Select(o => o.LimitPrice).FirstOrDefault(v => v.HasValue);

            if (rec.PlannedSlPx.HasValue && PointValue.TryGetValue(product, out var pv))
            {
                var riskPerCt = Math.Abs(entryPx - rec.PlannedSlPx.Value) * pv;
                if (riskPerCt > 0)
                    rec.RMultiple = Math.Round(rec.NetPnl / p.Qty / riskPerCt, 2);
            }
            if (TickSize.TryGetValue(product, out var ts) && ts > 0)
                rec.ResultTicks = (int)Math.Round((exitPx - entryPx) * (isLong ? 1 : -1) / ts);
            yield return rec;
        }
    }

    static string SessionOf(DateTime et) => et.Hour switch
    {
        >= 18 or < 2 => "Asia", >= 2 and < 8 => "London",
        >= 8 and < 12 => "NY AM", >= 12 and < 17 => "NY PM", _ => "Globex"
    };
}
