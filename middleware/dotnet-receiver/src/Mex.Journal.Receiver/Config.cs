// D-79 · ConfigProvider — de herlaadbare bron voor `AccountQty`,
// `AccountBlockGate` en `AccountRiskGate`. Fase 1 van het herijkingsplan.
//
// Waarom nodig. Vandaag lezen die drie klassen hun waarden in een static
// constructor uit env-variabelen. Een wijziging vraagt een `systemctl
// restart mex-receiver`. Ferry's antwoord 8 vraagt om optie b: een
// configuratiebron die zónder herstart mee-beweegt.
//
// Wat dit is (fase 1) en wat het NIET is (fase 2 en verder):
//   ✔ leest `docs/schema-config.md`-shape uit een JSON-file
//   ✔ polls de file elke `MEX_CONFIG_POLL_MS` ms (default 5000) en herlaadt
//     op een gewijzigde mtime
//   ✔ biedt een thread-safe `Current`-snapshot
//   ✔ per-account waarden (status, caps, contracts) worden geconsulteerd door
//     de gates in `Program.cs`; het env-pad blijft als vangnet zolang D-81
//     de migratie niet gedaan heeft
//   ✘ geen validatie of laatst-goede-terugval bij een kapotte file — dat is D-80
//   ✘ geen auditspoor — dat is D-81
//   ✘ geen HTTP-schrijfpad — dat is D-82
//
// Zelfde gedrag, andere bron. Als de configuratiefile ontbreekt of leeg is,
// werkt de receiver **exact als vandaag** — de env-vars blijven de waarheid.
// Zodra een account in de file voorkomt, wint de file voor dat account.
using System.Text.Json;
using System.Text.Json.Nodes;

namespace Mex.Journal.Receiver;

// -----------------------------------------------------------------------
// Snapshot-DTO's — bewust minimaal. Alleen wat de gates in fase 1 lezen.
// De volledige shape van schema-config.md komt later; nu levert een fase-1
// consumer alleen de velden die de bestaande gates raken.
// -----------------------------------------------------------------------

public sealed class AccountConfig
{
    // "active" · "halted" · "blocked" · "archived". Zie schema §3.
    // `halted` blokkeert entries via AccountRiskGate; `blocked` doet nog niets
    // in fase 1 en wacht op fase 4 (T2). Bewust conservatief: een onbekende
    // status = "active" — een fout in de config mag geen orders blokkeren.
    public string Status { get; init; } = "active";

    // Ferry's "wat de middleware bewaakt" (schema §3, §6). null = geen cap.
    public int? DailyEntryCap { get; init; }

    // D-53's vangnet. Buiten de settings-tab per schema §3, maar wel in de
    // file zodat D-79 hem ook hot kan reloaden. Env-var blijft de bron bij
    // ontbrekende file — dit is een override, geen vervanger.
    public int? Contracts { get; init; }

    // Reserveringen voor latere fasen — leeg gelaten in de reader zodat er
    // geen dead code ontstaat. Volgt schema §3 op het moment dat D-91/D-92
    // ze consumeren.
}

public sealed class ConfigDocument
{
    public int Version { get; init; }
    public string UpdatedAt { get; init; } = "";
    public string UpdatedBy { get; init; } = "";

    // account-id (bv. "PAAPEX2700250000013") → per-account config
    public IReadOnlyDictionary<string, AccountConfig> Accounts { get; init; }
        = new Dictionary<string, AccountConfig>();

    // fleet-brede default; per schema §4. null → geen default cap.
    public int? DefaultEntryCap { get; init; }

    public static readonly ConfigDocument Empty = new();
}

// -----------------------------------------------------------------------
// ConfigProvider — één static entry-point. Start() eenmalig bij boot.
// Poll-based i.p.v. FileSystemWatcher: op Linux is de watcher fragiel
// (missed events op bind-mounts, glibc-versie-gedoe) en 5s is voor deze
// low-write source ruim genoeg. Boring en robuust wint hier.
// -----------------------------------------------------------------------

public static class ConfigProvider
{
    static readonly object _lock = new();
    static volatile ConfigDocument _current = ConfigDocument.Empty;
    static DateTime _lastMtimeUtc = DateTime.MinValue;
    static long _lastLength = -1;

    static Timer? _timer;
    static string _path = "";
    static int _pollMs = 5000;

    /// <summary>Snapshot van de laatst succesvol geladen configuratie.</summary>
    public static ConfigDocument Current => _current;

    /// <summary>Pad waar de configuratie vandaan komt (na Start()).</summary>
    public static string Path => _path;

    /// <summary>Start de poll-loop. Idempotent — meerdere calls doen niks.</summary>
    public static void Start()
    {
        lock (_lock)
        {
            if (_timer is not null) return;
            _path = Environment.GetEnvironmentVariable("MEX_CONFIG_PATH")
                ?? "/root/mex-config/mex.json";
            if (int.TryParse(Environment.GetEnvironmentVariable("MEX_CONFIG_POLL_MS"), out var ms)
                && ms >= 500)
                _pollMs = ms;
            // Direct één keer proberen te laden, ongeacht poll-interval — anders
            // is de eerste 5s van de service altijd op env-waarden zonder file.
            TryReload();
            _timer = new Timer(_ => TryReload(), null, _pollMs, _pollMs);
            Console.Error.WriteLine($"[config] provider started · path={_path} · poll={_pollMs}ms");
        }
    }

    /// <summary>Alleen voor tests / handmatige triggers. Doet één reload-poging.</summary>
    public static void ForceReload() => TryReload();

    static void TryReload()
    {
        try
        {
            var info = new FileInfo(_path);
            if (!info.Exists)
            {
                if (_current != ConfigDocument.Empty)
                {
                    // File verdween — val terug op leeg, zodat env-vangnet weer
                    // wint. Ongewoon maar mogelijk (moved, atomic replace half).
                    Console.Error.WriteLine($"[config] file missing, reverting to empty · path={_path}");
                    lock (_lock)
                    {
                        _current = ConfigDocument.Empty;
                        _lastMtimeUtc = DateTime.MinValue;
                        _lastLength = -1;
                    }
                }
                return;
            }
            if (info.LastWriteTimeUtc == _lastMtimeUtc && info.Length == _lastLength)
                return;

            var text = File.ReadAllText(info.FullName);
            var parsed = Parse(text);
            if (parsed is null) return;   // parse-fout gelogd door Parse()

            lock (_lock)
            {
                _current = parsed;
                _lastMtimeUtc = info.LastWriteTimeUtc;
                _lastLength = info.Length;
            }
            Console.Error.WriteLine(
                $"[config] loaded v{parsed.Version} · accounts={parsed.Accounts.Count} · " +
                $"defaultCap={parsed.DefaultEntryCap?.ToString() ?? "—"} · updatedBy={parsed.UpdatedBy}");
        }
        catch (Exception ex)
        {
            // D-80 zal hier op landen (laatst-goede + luide melding). Voor
            // fase 1: log naar stderr en houd de bestaande snapshot. Zelfs
            // een kapotte file mag geen orders blokkeren of doen ontsnappen.
            Console.Error.WriteLine($"[config] reload failed, keeping last-good v{_current.Version}: {ex.Message}");
        }
    }

    // Parser is bewust JsonNode-based (zelfde patroon als Program.cs voor
    // TradingView-payloads). Geen source-generated System.Text.Json — dan
    // ontstaan nullable-annotation-issues die niets aan het gedrag toevoegen.
    static ConfigDocument? Parse(string text)
    {
        JsonNode? root;
        try { root = JsonNode.Parse(text); }
        catch (JsonException ex)
        {
            Console.Error.WriteLine($"[config] JSON parse failed: {ex.Message}");
            return null;
        }
        if (root is not JsonObject obj) return null;

        var accounts = new Dictionary<string, AccountConfig>(StringComparer.OrdinalIgnoreCase);
        if (obj["accounts"] is JsonObject accs)
        {
            foreach (var kv in accs)
            {
                if (string.IsNullOrEmpty(kv.Key) || kv.Value is not JsonObject a) continue;
                accounts[kv.Key] = new AccountConfig
                {
                    Status = a["status"]?.ToString()?.ToLowerInvariant() ?? "active",
                    DailyEntryCap = ReadIntFromCaps(a["caps"], "entries_per_day"),
                    Contracts = ReadIntOrNull(a["contracts"]),
                };
            }
        }

        int? defaultCap = null;
        if (obj["defaults"] is JsonObject defs)
            defaultCap = ReadIntFromCaps(defs["caps"], "entries_per_day");

        return new ConfigDocument
        {
            Version = ReadIntOrNull(obj["version"]) ?? 0,
            UpdatedAt = obj["updated"]?.ToString() ?? "",
            UpdatedBy = obj["updated_by"]?.ToString() ?? "",
            Accounts = accounts,
            DefaultEntryCap = defaultCap,
        };
    }

    static int? ReadIntFromCaps(JsonNode? capsNode, string key)
    {
        if (capsNode is not JsonObject caps) return null;
        return ReadIntOrNull(caps[key]);
    }

    static int? ReadIntOrNull(JsonNode? n)
    {
        if (n is null) return null;
        try
        {
            var v = n.GetValue<double>();
            if (double.IsNaN(v) || v < 0) return null;
            return (int)v;
        }
        catch { return null; }
    }
}
