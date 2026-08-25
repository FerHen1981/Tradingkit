using Mex.Journal.Models;
namespace Mex.Journal.Adapters;

/// <summary>Eén interface voor alle bronnen (matrix: Tradovate, Quantower, backtest, generiek).
/// Downstream (dedupe, recon, Notion-sync) kent alleen TradeRecord.</summary>
public interface ITradeSourceAdapter
{
    string SourceName { get; }
    /// <summary>Kan deze adapter iets met dit pad (bestand of map)?</summary>
    bool CanHandle(string path);
    IReadOnlyList<TradeRecord> Read(string path);
}
