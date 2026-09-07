namespace Mex.Journal;

/// <summary>Minimal RFC4180 reader — handles quoted fields with commas/newlines.</summary>
public static class Csv
{
    public static List<Dictionary<string, string>> ReadFile(string path)
    {
        var rows = Parse(File.ReadAllText(path));
        if (rows.Count == 0) return new();
        var header = rows[0];
        var result = new List<Dictionary<string, string>>(rows.Count - 1);
        foreach (var row in rows.Skip(1))
        {
            if (row.Count == 1 && string.IsNullOrWhiteSpace(row[0])) continue;
            var d = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
            for (int i = 0; i < header.Count && i < row.Count; i++) d[header[i].Trim()] = row[i];
            result.Add(d);
        }
        return result;
    }

    static List<List<string>> Parse(string text)
    {
        var rows = new List<List<string>>();
        var row = new List<string>();
        var field = new System.Text.StringBuilder();
        bool inQ = false;
        for (int i = 0; i < text.Length; i++)
        {
            char c = text[i];
            if (inQ)
            {
                if (c == '"' && i + 1 < text.Length && text[i + 1] == '"') { field.Append('"'); i++; }
                else if (c == '"') inQ = false;
                else field.Append(c);
            }
            else if (c == '"') inQ = true;
            else if (c == ',') { row.Add(field.ToString()); field.Clear(); }
            else if (c == '\r') { }
            else if (c == '\n') { row.Add(field.ToString()); field.Clear(); rows.Add(row); row = new(); }
            else field.Append(c);
        }
        if (field.Length > 0 || row.Count > 0) { row.Add(field.ToString()); rows.Add(row); }
        return rows;
    }

    public static decimal Money(string s)
    {
        s = s.Replace("$", "").Replace(",", "").Trim();
        if (s.Length == 0) return 0m;
        bool neg = s.StartsWith("(") && s.EndsWith(")");
        if (neg) s = s[1..^1];
        return decimal.TryParse(s, System.Globalization.NumberStyles.Any,
            System.Globalization.CultureInfo.InvariantCulture, out var v) ? (neg ? -v : v) : 0m;
    }
}
