namespace Mex.Journal.Models;

/// <summary>Canoniek trade-record — 1:1 met het CSV-contract (zie docs/csv_contract.md).</summary>
public class TradeRecord
{
    public string TradeId = ""; public string Source = "Live"; public string Bot = "";
    public string Account = ""; public string RunId = ""; public string Instrument = "";
    public string Contract = ""; public string Direction = ""; public int Qty;
    public DateTime? EntryTimeUtc; public DateTime? ExitTimeUtc;
    public decimal EntryPrice; public decimal ExitPrice;
    public decimal GrossPnl; public decimal Fees; public decimal NetPnl => GrossPnl - Fees;
    public decimal? RMultiple; public decimal? MfeUsd; public decimal? MaeUsd;
    public string ExitReason = ""; public string Session = ""; public string Regime = "";
    public string Signal = ""; public string Intervention = "None";
    public decimal? InterventionCost; public string Notes = "";
    public decimal? PlannedSlPx; public decimal? PlannedTpPx; public string ApexTradeDate = "";
    public string BuyFillId = ""; public string SellFillId = "";
    public int? ResultTicks; public decimal? DurationMin;

    public static readonly string[] Columns = {
        "trade_id","source","bot","account","run_id","instrument","contract","direction","qty",
        "entry_time","exit_time","entry_price","exit_price","gross_pnl","fees","net_pnl",
        "r_multiple","mfe_usd","mae_usd","exit_reason","session","regime","signal",
        "intervention","intervention_cost","notes","planned_sl_px","planned_tp_px","apex_trade_date" };

    public string ToCsvRow()
    {
        static string Q(string s) => s.Contains(',') || s.Contains('"')
            ? "\"" + s.Replace("\"", "\"\"") + "\"" : s;
        static string D(decimal? v) => v?.ToString("0.####", System.Globalization.CultureInfo.InvariantCulture) ?? "";
        static string T(DateTime? t) => t?.ToString("yyyy-MM-ddTHH:mm:ssZ") ?? "";
        return string.Join(",", Q(TradeId), Source, Q(Bot), Account, RunId, Instrument, Contract,
            Direction, Qty.ToString(), T(EntryTimeUtc), T(ExitTimeUtc), D(EntryPrice), D(ExitPrice),
            D(GrossPnl), D(Fees), D(NetPnl), D(RMultiple), D(MfeUsd), D(MaeUsd), ExitReason, Session,
            Regime, Q(Signal), Intervention, D(InterventionCost), Q(Notes), D(PlannedSlPx), D(PlannedTpPx), ApexTradeDate);
    }
}
