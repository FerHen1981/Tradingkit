using Mex.Journal.Models;
namespace Mex.Journal.Recon;

public class ReconResult
{
    public int FillAlerts, MatchedFillAlerts;
    public List<AlertEvent> UnmatchedFillAlerts = new();
    public int Fills, FillsWithAlert;
    public Dictionary<string, int> BlockedByReason = new();
    public Dictionary<string, int> DeliveryFailures = new();
    public List<string> AccountsWithoutAlerts = new();
    public int TotalAlerts, FailedDeliveries;
}

/// <summary>Vierlaags-keten: intentie (alerts) ↔ executie (fills). Orders/pairing-verrijking zit in de adapter.</summary>
public static class ReconciliationEngine
{
    public static ReconResult Run(List<AlertEvent> alerts, List<TradeRecord> trades,
        Dictionary<string, List<DateTime>> fillTimesUtcByAccount, TimeSpan tolerance)
    {
        var res = new ReconResult { TotalAlerts = alerts.Count };
        res.FailedDeliveries = alerts.Count(a => a.DeliveryFailed);
        foreach (var g in alerts.Where(a => a.DeliveryFailed)
                     .GroupBy(a => a.DeliveryStatus.Length > 40 ? a.DeliveryStatus[..40] : a.DeliveryStatus))
            res.DeliveryFailures[g.Key] = g.Count();

        foreach (var a in alerts.Where(a => a.Kind == AlertKind.Blocked))
        {
            var m = System.Text.RegularExpressions.Regex.Match(a.Description, @"blocked by:\s*(.+)$");
            var reason = m.Success ? m.Groups[1].Value.Trim() : "(onbekend)";
            res.BlockedByReason[reason] = res.BlockedByReason.GetValueOrDefault(reason) + 1;
        }

        var fillAlerts = alerts.Where(a => a.Kind == AlertKind.Fill).ToList();
        res.FillAlerts = fillAlerts.Count;
        foreach (var a in fillAlerts)
        {
            if (fillTimesUtcByAccount.TryGetValue(a.Account, out var times)
                && times.Any(t => (t - a.TimeUtc).Duration() <= tolerance))
                res.MatchedFillAlerts++;
            else res.UnmatchedFillAlerts.Add(a);
        }

        var alertAccounts = fillAlerts.Select(a => a.Account).ToHashSet();
        res.AccountsWithoutAlerts = fillTimesUtcByAccount.Keys
            .Where(acc => !alertAccounts.Contains(acc)).OrderBy(x => x).ToList();
        res.Fills = fillTimesUtcByAccount.Values.Sum(v => v.Count);
        return res;
    }
}
