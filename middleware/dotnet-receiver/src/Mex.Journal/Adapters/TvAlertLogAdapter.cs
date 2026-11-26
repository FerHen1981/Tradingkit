using System.Globalization;
using System.Text.RegularExpressions;
using Mex.Journal.Models;
namespace Mex.Journal.Adapters;

/// <summary>Parser voor TradingView alert-log-exports (Discord-payload-variant).</summary>
public static class TvAlertLogAdapter
{
    static readonly Regex NameRx = new(@"DISC (.+?) \((\w+)", RegexOptions.Compiled);
    static readonly Regex TitleRx = new("\"title\":\"([^\"]+)\"", RegexOptions.Compiled);
    static readonly Regex DescRx = new("\"description\":\"([^\"]+)\"", RegexOptions.Compiled);

    public static List<AlertEvent> Read(string path)
    {
        var events = new List<AlertEvent>();
        foreach (var r in Csv.ReadFile(path))
        {
            if (!DateTime.TryParse(r.GetValueOrDefault("Time", ""), CultureInfo.InvariantCulture,
                DateTimeStyles.AdjustToUniversal | DateTimeStyles.AssumeUniversal, out var t)) continue;
            var name = r.GetValueOrDefault("Name", "");
            var m = NameRx.Match(name);
            var desc = r.GetValueOrDefault("Description", "");
            var title = TitleRx.Match(desc) is { Success: true } tm ? tm.Groups[1].Value : "";
            var body = DescRx.Match(desc) is { Success: true } dm ? dm.Groups[1].Value : "";
            events.Add(new AlertEvent(t,
                r.GetValueOrDefault("Ticker", "").Split(',')[0],
                m.Success ? m.Groups[1].Value : "?",
                m.Success ? m.Groups[2].Value : "?",
                Classify(title), title, body,
                r.GetValueOrDefault("Webhook status", "")));
        }
        return events;
    }

    static AlertKind Classify(string title) =>
        title.Contains("SIGNAL BLOCKED") ? AlertKind.Blocked :
        title.Contains("FILL") ? AlertKind.Fill :
        title.Contains("EXIT") ? AlertKind.Exit :
        title.Contains("LIMIT EXPIRED") ? AlertKind.LimitExpired :
        title.Contains("LIMIT") ? AlertKind.Limit :
        title.Contains("DAY HALT") ? AlertKind.DayHalt :
        title.Contains("AUTO FLAT") ? AlertKind.AutoFlat :
        title.Contains("REGIME") ? AlertKind.Regime :
        title.Contains("CONFIG") ? AlertKind.Config : AlertKind.Other;
}
