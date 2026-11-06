// D-85 · SecretsStore — een aparte kluis voor tokens, weburls en andere
// waarden waar `schema-config.md` §5 naar verwijst via `_ref`-sleutels.
//
// Waarom apart van `ConfigProvider`. De config-file wordt via
// `GET /api/config` (D-82) helemaal teruggegeven en verschijnt in het
// auditspoor (D-81). Een geheim dat één keer in die stroom belandt is
// permanent gelekt — audit.log is append-only. De kluis moet daarom een
// **eigen** bron zijn die die twee kanalen niet raakt:
//
//   ✔ schrijven mag via `PUT /api/secrets/{name}`
//   ✔ lezen kan alleen NAMES via `GET /api/secrets`
//   ✔ de waarde zelf is alleen bereikbaar via `SecretsStore.Get(name)`
//     vanuit de receiver-code (bijv. straks D-87's `PmtPayloadBuilder`)
//   ✘ de rauwe file wordt NOOIT via een endpoint teruggegeven
//   ✘ de waarde wordt NOOIT in `audit.log` of stderr gelogd — bewust,
//     niet toevallig
//
// Format op disk: één JSON-object, `{"name": "value"}`. Atomair geschreven
// (tmp + rename). Pad: `MEX_SECRETS_PATH`, default `/root/mex-config/secrets.json`.
// Bij ontbreken van de file: geen geheimen, `Get()` retourneert `null`. Dat
// is opzet — schema §5 verbiedt aannames over "wat als de kluis leeg is".
// Alleen dié waarden die expliciet zijn ingesteld, kunnen worden opgehaald.
using System.Text.Json;
using System.Text.Json.Nodes;

namespace Mex.Journal.Receiver;

public static class SecretsStore
{
    static readonly object _lock = new();
    static volatile IReadOnlyDictionary<string, string> _current
        = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
    // Metadata die WEL via GET /api/secrets terug mag — namen + timestamps,
    // maar nooit waarden.
    static volatile IReadOnlyDictionary<string, DateTime> _lastWrites
        = new Dictionary<string, DateTime>(StringComparer.OrdinalIgnoreCase);

    static DateTime _lastMtimeUtc = DateTime.MinValue;
    static long _lastLength = -1;

    static Timer? _timer;
    static string _path = "";
    static int _pollMs = 5000;

    public static string Path => _path;

    /// <summary>Opent de kluis, herlaadt hem elke `MEX_CONFIG_POLL_MS` ms
    /// (dezelfde knop als ConfigProvider). Idempotent.</summary>
    public static void Start()
    {
        lock (_lock)
        {
            if (_timer is not null) return;
            _path = Environment.GetEnvironmentVariable("MEX_SECRETS_PATH")
                ?? "/root/mex-config/secrets.json";
            if (int.TryParse(Environment.GetEnvironmentVariable("MEX_CONFIG_POLL_MS"), out var ms)
                && ms >= 500)
                _pollMs = ms;
            TryReload();
            _timer = new Timer(_ => TryReload(), null, _pollMs, _pollMs);
            Console.Error.WriteLine(
                $"[secrets] store started · path={_path} · poll={_pollMs}ms · loaded={_current.Count}");
        }
    }

    /// <summary>Ophalen van een geheim op naam. Retourneert `null` als de
    /// naam niet in de kluis staat, of als de kluis leeg is. Loopt bewust
    /// niet terug op env-vars — de kluis is de enige bron, zodat er straks
    /// nooit een tweede waarheid ontstaat.</summary>
    public static string? Get(string name)
    {
        if (string.IsNullOrEmpty(name)) return null;
        var snap = _current;
        return snap.TryGetValue(name, out var v) ? v : null;
    }

    /// <summary>Alle namen van geheimen die momenteel in de kluis staan.
    /// Nooit waarden. Wordt door `GET /api/secrets` teruggegeven.</summary>
    public static IReadOnlyList<SecretMetadata> ListMetadata()
    {
        var snap = _current;
        var writes = _lastWrites;
        var list = new List<SecretMetadata>(snap.Count);
        foreach (var name in snap.Keys)
        {
            writes.TryGetValue(name, out var ts);
            list.Add(new SecretMetadata { Name = name, LastWrittenUtc = ts });
        }
        list.Sort((a, b) => string.CompareOrdinal(a.Name, b.Name));
        return list;
    }

    // Schrijfacties: één naam per keer. Volledige file-vervanging zou een
    // grotere blast-radius geven (per ongeluk alles wissen); PUT per naam
    // is de veilige eenheid. `value` mag leeg zijn — DELETE.
    public static async Task WriteAsync(string name, string? value)
    {
        if (string.IsNullOrEmpty(name))
            throw new ArgumentException("name is empty", nameof(name));

        var updated = new Dictionary<string, string>(_current, StringComparer.OrdinalIgnoreCase);
        var writes = new Dictionary<string, DateTime>(_lastWrites, StringComparer.OrdinalIgnoreCase);
        if (string.IsNullOrEmpty(value))
        {
            updated.Remove(name);
            writes.Remove(name);
        }
        else
        {
            updated[name] = value;
            writes[name] = DateTime.UtcNow;
        }

        await PersistAsync(updated);

        lock (_lock)
        {
            _current = updated;
            _lastWrites = writes;
        }
        // Bewust NIETS loggen over welk secret is gewijzigd (naam is oké,
        // waarde niet). audit.log heeft geen aanraakregel — die woont in
        // de config, niet hier. Wie wijzigde blijkt uit het HTTP-request
        // en die logs sluiten geen waarde in.
    }

    // ------------------------------------------------------------------
    // Interne mechanica
    // ------------------------------------------------------------------

    static void TryReload()
    {
        try
        {
            if (!File.Exists(_path)) return;
            var info = new FileInfo(_path);
            if (info.LastWriteTimeUtc == _lastMtimeUtc && info.Length == _lastLength)
                return;

            var text = File.ReadAllText(_path);
            var parsed = Parse(text);
            if (parsed is null)
            {
                // Kapot bestand: laatst-goede behouden (net als Config).
                Console.Error.WriteLine($"[secrets] parse failed, keeping last-good ({_current.Count} secrets)");
                return;
            }

            lock (_lock)
            {
                _current = parsed;
                _lastMtimeUtc = info.LastWriteTimeUtc;
                _lastLength = info.Length;
            }
            Console.Error.WriteLine($"[secrets] loaded {_current.Count} secrets");
        }
        catch (Exception ex)
        {
            Console.Error.WriteLine($"[secrets] reload failed, keeping last-good: {ex.Message}");
        }
    }

    static IReadOnlyDictionary<string, string>? Parse(string text)
    {
        JsonNode? root;
        try { root = JsonNode.Parse(text); }
        catch (JsonException) { return null; }
        if (root is not JsonObject obj) return null;
        var dict = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
        foreach (var kv in obj)
        {
            if (string.IsNullOrEmpty(kv.Key)) continue;
            if (kv.Value is null) continue;
            var s = kv.Value.ToString();
            if (!string.IsNullOrEmpty(s))
                dict[kv.Key] = s;
        }
        return dict;
    }

    static async Task PersistAsync(IReadOnlyDictionary<string, string> data)
    {
        var obj = new JsonObject();
        foreach (var kv in data)
            obj[kv.Key] = kv.Value;
        var text = obj.ToJsonString(new JsonSerializerOptions { WriteIndented = true });
        var dir = System.IO.Path.GetDirectoryName(_path);
        if (!string.IsNullOrEmpty(dir)) Directory.CreateDirectory(dir);
        var tmp = _path + ".tmp";
        await File.WriteAllTextAsync(tmp, text);
        File.Move(tmp, _path, overwrite: true);

        // Verwerf directe herlees zodat onze in-memory snapshot mét de nieuwe
        // waarde is en niet uit sync loopt met disk. Zet mtime/length op de
        // net-geschreven waarden.
        var info = new FileInfo(_path);
        lock (_lock)
        {
            _lastMtimeUtc = info.LastWriteTimeUtc;
            _lastLength = info.Length;
        }
    }
}

public sealed class SecretMetadata
{
    public string Name { get; init; } = "";
    public DateTime LastWrittenUtc { get; init; }
}
