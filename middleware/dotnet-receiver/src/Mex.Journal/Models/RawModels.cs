namespace Mex.Journal.Models;

public record Fill(string FillId, string Account, string Product, string Contract,
    string Side, int Qty, decimal Price, DateTime TimestampUtc, string TradeDate, decimal Commission);

public record BrokerOrder(string OrderId, string Account, string Product, string Contract,
    string Side, string Type, string Status, int Qty, decimal? LimitPrice, decimal? StopPrice,
    decimal? AvgFillPrice, DateTime? PlacedEt, DateTime? FillTimeEt, string Text);

public record PerfPair(string Account, decimal Pnl, int Qty, string BuyFillId, string SellFillId,
    decimal BoughtPx, decimal SoldPx, DateTime BoughtEt, DateTime SoldEt);

public enum AlertKind { Limit, Fill, Exit, Blocked, DayHalt, AutoFlat, LimitExpired, Regime, Config, Other }

public record AlertEvent(DateTime TimeUtc, string Ticker, string Bot, string Account,
    AlertKind Kind, string Title, string Description, string DeliveryStatus)
{
    public bool DeliveryFailed => DeliveryStatus.Contains("failed", StringComparison.OrdinalIgnoreCase);
}
