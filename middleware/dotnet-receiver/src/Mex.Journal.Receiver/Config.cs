// D-79 + D-80 + D-81 · ConfigProvider — de herlaadbare bron voor `AccountQty`,
// `AccountBlockGate` en `AccountRiskGate`. Fase 1 van het herijkingsplan.
//
// Waarom nodig. Vandaag lezen die drie klassen hun waarden in een static
// constructor uit env-variabelen. Een wijziging vraagt een `systemctl
// restart mex-receiver`. Ferry's antwoord 8 vraagt om optie b: een
// configuratiebron die zónder herstart mee-beweegt.
//
// Wat dit is (fase 1 · D-79 + D-80 + D-81) en wat het NIET is (fase 2+):
//   ✔ leest `docs/schema-config.md`-shape uit een JSON-file
//   ✔ polls de file elke `MEX_CONFIG_POLL_MS` ms (default 5000) en herlaadt
//     op een gewijzigde mtime
//   ✔ biedt een thread-safe `Current`-snapshot
//   ✔ per-account waarden (status, caps, contracts) worden geconsulteerd door
//     de gates in `Program.cs`; het env-pad blijft als vangnet zolang de
//     migratie niet volledig heeft plaatsgevonden
//   ✔ D-80 · valideert een nieuwe file vóór hij `Current` wordt; op fout
//     blijft de laatst-goede staan, een luide melding gaat naar Discord
//     (rate-limited per unieke bad-file-mtime zodat een blijvend kapotte
//     file niet spammt)
//   ✔ D-81 · append-only auditspoor: elke laad-poging (geslaagd én afgewezen)
//     krijgt een JSONL-regel met wie/wat/wanneer/vorige-versie en bij een
//     wijziging een diff van gewijzigde velden. Bron voor "waarom is deze
//     order zo gerouteerd" achteraf reconstrueerbaar.
//   ✘ geen HTTP-schrijfpad — dat is D-82
//
// Zelfde gedrag, andere bron. Als de configuratiefile ontbreekt of leeg is,
// werkt de receiver **exact als vandaag** — de env-vars blijven de waarheid.
// Zodra een account in de file voorkomt en de file valideert, wint de file
// voor dat account. Een kapotte file kan **nooit** een order beïnvloeden —
// de snapshot swapt atomair pas nadat Validate() slaagt.
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

    // D-80 · rate-limit voor de luide melding. Sla de mtime+length op van de
    // laatste file waarvoor we een alarm hebben afgevuurd. Blijft de kapotte
    // file staan, dan gaat er geen tweede melding uit — anders overspoelt één
    // fout het Discord-kanaal en verliezen we het signaal in de ruis. Wordt
    // gereset zodra een gezonde file laadt (dan is de reeks fouten voorbij).
    static DateTime _lastAlarmMtimeUtc = DateTime.MinValue;
    static long _lastAlarmLength = -1;
    // D-81 SM-review · aparte boolean voor het "file is weg"-alarm zodat het
    // niet interfereert met de mtime+length rate-limit voor parse/validate-
    // rejects. Reset op elke gezonde load.
    static bool _missingAlarmFired = false;
    static Action<string, string>? _alarm;

    static Timer? _timer;
    static string _path = "";
    static int _pollMs = 5000;

    /// <summary>Snapshot van de laatst succesvol geladen configuratie.</summary>
    public static ConfigDocument Current => _current;

    /// <summary>Pad waar de configuratie vandaan komt (na Start()).</summary>
    public static string Path => _path;

    /// <summary>Start de poll-loop. Idempotent — meerdere calls doen niks.
    /// <paramref name="alarm"/> wordt aangeroepen (titel, beschrijving) op elke
    /// unieke parse- of validatiefout. Zonder alarm-delegate blijft alles in
    /// stderr; met alarm gaat er ook een luide melding uit — dat is D-80.
    /// </summary>
    public static void Start(Action<string, string>? alarm = null)
    {
        lock (_lock)
        {
            if (_timer is not null) return;
            _alarm = alarm;
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

    /// <summary>D-82 · Publieke variant van de parser + validator. Wordt door
    /// de Config-API gebruikt om een inkomende PUT te toetsen vóór hij wordt
    /// weggeschreven — anders schrijven we een file die 5 seconden later door
    /// TryReload wordt afgewezen en krijgt de gebruiker geen directe feedback.</summary>
    public static (bool Ok, string Error) TryParseAndValidate(string text)
    {
        var parsed = Parse(text, out var parseError);
        if (parsed is null) return (false, parseError ?? "unknown parse error");
        return ConfigValidator.Validate(parsed);
    }

    /// <summary>D-82 · Rauwe file-inhoud voor de GET-endpoint. Leest van disk
    /// zodat de client precies ziet wat er is opgeslagen — inclusief velden die
    /// de fase-1 reader vandaag nog niet consumeert (channels, defaults.widget,
    /// notion.*). Zonder file: null zodat de endpoint 204 kan sturen.</summary>
    public static string? ReadRawOrNull()
    {
        try
        {
            if (!File.Exists(_path)) return null;
            return File.ReadAllText(_path);
        }
        catch { return null; }
    }

    static void TryReload()
    {
        FileInfo info;
        try { info = new FileInfo(_path); }
        catch (Exception ex)
        {
            Console.Error.WriteLine($"[config] path check failed, keeping last-good v{_current.Version}: {ex.Message}");
            return;
        }

        if (!info.Exists)
        {
            // D-81 SM-review, twee punten:
            // (a) een verdwenen file was tot deze fix stil (alleen stderr).
            //     Weg-zijn is minstens zo ernstig als een kapotte file, dus
            //     we schieten hier hetzelfde alarm af.
            // (b) 🔴 VOLGORDE-RISICO. Terugvallen op ConfigDocument.Empty
            //     was veilig zolang de env-vangnet nog gevuld is. Na de
            //     D-81-migratie is de env leeg — dan betekent "empty" GEEN
            //     regels op ELK account: kill-switch-gedrag zonder bedoeling.
            //     **We houden nu de laatst-goede snapshot vast** en laten
            //     `_lastMtimeUtc`/`_lastLength` staan. Zo blijven de gates
            //     bediend tot de file terugkomt of tot Ferry expliciet
            //     herstart (waarna Empty de eerste snapshot is en de env-
            //     vangnet doet wat hij moet doen).
            if (_current == ConfigDocument.Empty)
                return;   // niets te verliezen, geen alarm nodig
            if (_missingAlarmFired)
                return;   // al gealarmeerd voor deze verdwijning — wacht op verandering

            var stderrLine =
                $"[config] file missing, keeping last-good v{_current.Version} · path={_path}";
            Console.Error.WriteLine(stderrLine);

            lock (_lock)
            {
                _missingAlarmFired = true;
            }

            var alarm = _alarm;
            if (alarm is not null)
            {
                var current = _current;
                var title = "⚠️ Config-file verdwenen — draai door op laatst-goede";
                var desc =
                    $"**Reden:** file disappeared\n" +
                    $"**Pad:** `{_path}`\n" +
                    $"**Nog actief:** v{current.Version} ({current.Accounts.Count} accounts)\n\n" +
                    "De receiver draait door op de laatst-goede configuratie. Als je de env-migratie al hebt gedaan, is dit géén veilige stille terugval — er staan geen envs meer als vangnet.";
                try { alarm(title, desc); }
                catch (Exception ex) { Console.Error.WriteLine($"[config] alarm delivery failed: {ex.Message}"); }
            }

            // D-81 · auditspoor krijgt ook de "disappeared"-lijn.
            try
            {
                ConfigAudit.AppendMissing(_current, _path);
            }
            catch (Exception ex) { Console.Error.WriteLine($"[config] audit write failed: {ex.Message}"); }

            return;
        }
        if (info.LastWriteTimeUtc == _lastMtimeUtc && info.Length == _lastLength)
            return;

        // Vanaf hier: nieuwe file, dus lezen + parse + valideren + (bij goed)
        // atomair swappen. Bij fout: last-good blijft staan en het alarm
        // schiet één keer af voor deze unieke mtime+length combinatie.

        string text;
        try { text = File.ReadAllText(info.FullName); }
        catch (Exception ex)
        {
            FailAndMaybeAlarm(info, "read failed", ex.Message);
            return;
        }

        var parsed = Parse(text, out var parseError);
        if (parsed is null)
        {
            FailAndMaybeAlarm(info, "parse failed", parseError ?? "unknown parse error");
            return;
        }

        var (ok, validateError) = ConfigValidator.Validate(parsed);
        if (!ok)
        {
            FailAndMaybeAlarm(info, "validation failed", validateError);
            return;
        }

        // D-80 · atomaire swap. Pas hier landt de nieuwe snapshot in `_current`,
        // zodat een half-gelezen of ongeldige file **nooit** door een gate wordt
        // geconsulteerd — de gates zien of de oude waarde of de nieuwe, nooit
        // iets ertussenin.
        ConfigDocument previous;
        lock (_lock)
        {
            previous = _current;
            _current = parsed;
            _lastMtimeUtc = info.LastWriteTimeUtc;
            _lastLength = info.Length;
            // Gezonde load → reset de alarm-cursor én de missing-vlag, zodat
            // een toekomstige fout of nieuwe verdwijning meteen een melding
            // krijgt in plaats van door de rate-limit gedempt te worden.
            _lastAlarmMtimeUtc = DateTime.MinValue;
            _lastAlarmLength = -1;
            _missingAlarmFired = false;
        }
        Console.Error.WriteLine(
            $"[config] loaded v{parsed.Version} · accounts={parsed.Accounts.Count} · " +
            $"defaultCap={parsed.DefaultEntryCap?.ToString() ?? "—"} · updatedBy={parsed.UpdatedBy}");

        // D-81 · Auditspoor. Elke wissel krijgt een regel met from→to +
        // een diff van gewijzigde velden. Faalt de write, dan gebeurt er
        // niets met de swap — het auditspoor mag de provider niet stukmaken.
        try { ConfigAudit.AppendLoaded(previous, parsed); }
        catch (Exception ex) { Console.Error.WriteLine($"[config] audit write failed: {ex.Message}"); }
    }

    // Log + eenmalige luide melding voor deze exacte bad-file (mtime + length).
    // De laatst-goede blijft draaien — dat is de kern van D-80's veiligheidseis
    // "er wordt geen order op een half geladen config gestuurd".
    static void FailAndMaybeAlarm(FileInfo info, string phase, string detail)
    {
        var stderrLine =
            $"[config] {phase} for {_path}, keeping last-good v{_current.Version}: {detail}";
        Console.Error.WriteLine(stderrLine);

        // D-81 · Auditspoor krijgt ook de reject-lijn — anders staat er straks een
        // gat in het verhaal ("de config ging van v2 naar v4, waar is v3 gebleven?").
        try { ConfigAudit.AppendRejected(_current, info, phase, detail); }
        catch (Exception ex) { Console.Error.WriteLine($"[config] audit write failed: {ex.Message}"); }

        // Rate-limit: alleen alarmeren als deze exacte (mtime+length) nog niet
        // aan de melding is geweest. Anders blijft een blijvend kapotte file
        // Discord vullen tot iemand hem repareert.
        if (info.LastWriteTimeUtc == _lastAlarmMtimeUtc && info.Length == _lastAlarmLength)
            return;

        lock (_lock)
        {
            _lastAlarmMtimeUtc = info.LastWriteTimeUtc;
            _lastAlarmLength = info.Length;
        }

        var alarm = _alarm;
        if (alarm is null) return;

        var current = _current;
        var title = "⚠️ Config afgewezen — draai door op laatst-goede";
        var desc =
            $"**Reden:** {phase}\n" +
            $"**Detail:** {Trunc(detail, 300)}\n" +
            $"**Pad:** `{_path}`\n" +
            $"**Bestand:** mtime={info.LastWriteTimeUtc:o}, {info.Length} bytes\n" +
            $"**Nog actief:** v{current.Version} ({current.Accounts.Count} accounts)\n\n" +
            "De receiver draait door op de laatst-goede configuratie. Geen order gebruikt de afgewezen file.";
        try { alarm(title, desc); }
        catch (Exception ex)
        {
            // Het alarm mag de provider zelf nooit stuk maken.
            Console.Error.WriteLine($"[config] alarm delivery failed: {ex.Message}");
        }
    }

    static string Trunc(string s, int max)
        => (s ?? "").Length <= max ? (s ?? "") : (s![..max] + "…");

    // Parser is bewust JsonNode-based (zelfde patroon als Program.cs voor
    // TradingView-payloads). Geen source-generated System.Text.Json — dan
    // ontstaan nullable-annotation-issues die niets aan het gedrag toevoegen.
    // D-80: geeft nu een foutstring terug via `out error` zodat `TryReload`
    // hem in het alarm kan meesturen.
    static ConfigDocument? Parse(string text, out string? error)
    {
        error = null;
        JsonNode? root;
        try { root = JsonNode.Parse(text); }
        catch (JsonException ex)
        {
            error = $"JSON parse: {ex.Message}";
            return null;
        }
        if (root is not JsonObject obj)
        {
            error = "top-level is not a JSON object";
            return null;
        }

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


// -----------------------------------------------------------------------
// D-80 · Validator. Werkt op een al-geparseerde `ConfigDocument`. Doet ver-
// volg-controles die verder gaan dan "is dit geldig JSON": versienummer,
// enum-waarden, integer-sanity. Faalt bij het eerste probleem — een pakket
// met acht fouten hoeft alleen zijn eerste te tonen; de reparatie legt de
// rest bloot.
//
// Contract: `Validate(doc)` → `(true, "")` als de config veilig kan draaien;
// anders `(false, "<reden>")`. Reden is een korte machine-leesbare tekst,
// ontworpen om in een Discord-melding leesbaar te zijn.
// -----------------------------------------------------------------------

public static class ConfigValidator
{
    static readonly HashSet<string> _statuses = new(StringComparer.OrdinalIgnoreCase)
    {
        "active", "halted", "blocked", "archived",
    };

    public static (bool Ok, string Reason) Validate(ConfigDocument doc)
    {
        if (doc is null) return (false, "document is null");
        if (doc.Version < 1)
            return (false, $"version must be >= 1 (got {doc.Version})");

        if (doc.DefaultEntryCap is int fd && fd < 0)
            return (false, $"defaults.caps.entries_per_day must be >= 0 (got {fd})");

        foreach (var (acct, cfg) in doc.Accounts)
        {
            if (string.IsNullOrWhiteSpace(acct))
                return (false, "account with empty id");
            if (!_statuses.Contains(cfg.Status))
                return (false, $"account {acct}: unknown status '{cfg.Status}' (allowed: {string.Join(", ", _statuses)})");
            if (cfg.DailyEntryCap is int cap && cap < 0)
                return (false, $"account {acct}: caps.entries_per_day must be >= 0 (got {cap})");
            if (cfg.Contracts is int c && c <= 0)
                return (false, $"account {acct}: contracts must be > 0 (got {c})");
        }

        return (true, "");
    }
}


// -----------------------------------------------------------------------
// D-81 · Auditspoor. Append-only JSONL, één regel per laad-poging (geslaagd
// of afgewezen). "Straks de enige manier om te reconstrueren waarom een
// order ergens heen ging" — dus geen truncatie, geen roterende bestanden,
// geen filtering. Je hoort dit later te kunnen lezen en zien welke config
// er op moment X actief was.
//
// Format:
//   {"ts":"…","phase":"loaded","from":1,"to":2,"updated_by":"…","diff":{…}}
//   {"ts":"…","phase":"rejected","kept":1,"reason":"validation failed",
//    "detail":"…","file_mtime":"…","file_size":123}
//
// Pad: `MEX_CONFIG_AUDIT_PATH` (default `/root/mex-config/audit.log`).
// Ontbreekt de map, dan maakt de audit hem aan. Faalt de write, dan wordt
// er stderr-gelogd — de config-swap zelf gaat door.
// -----------------------------------------------------------------------

public static class ConfigAudit
{
    static readonly object _writeLock = new();

    static string Path =>
        Environment.GetEnvironmentVariable("MEX_CONFIG_AUDIT_PATH")
        ?? "/root/mex-config/audit.log";

    public static void AppendLoaded(ConfigDocument previous, ConfigDocument current)
    {
        var diff = BuildDiff(previous, current);
        var record = new JsonObject
        {
            ["ts"] = DateTime.UtcNow.ToString("o"),
            ["phase"] = "loaded",
            ["from"] = previous.Version,
            ["to"] = current.Version,
            ["updated_by"] = current.UpdatedBy,
            ["updated_at"] = current.UpdatedAt,
            ["accounts_now"] = current.Accounts.Count,
            ["diff"] = diff,
        };
        Write(record);
    }

    public static void AppendRejected(ConfigDocument kept, FileInfo info, string phase, string detail)
    {
        var record = new JsonObject
        {
            ["ts"] = DateTime.UtcNow.ToString("o"),
            ["phase"] = "rejected",
            ["kept"] = kept.Version,
            ["reason"] = phase,
            ["detail"] = detail,
            ["file_mtime"] = info.LastWriteTimeUtc.ToString("o"),
            ["file_size"] = info.Length,
        };
        Write(record);
    }

    // D-81 SM-review · een file die verdwijnt is óók een gebeurtenis. Zonder
    // deze regel staat er straks een gat: "de config ging van v3 naar v3 en
    // dan verscheen ineens v4" — met de disappeared-regel weet je waarom.
    public static void AppendMissing(ConfigDocument kept, string path)
    {
        var record = new JsonObject
        {
            ["ts"] = DateTime.UtcNow.ToString("o"),
            ["phase"] = "disappeared",
            ["kept"] = kept.Version,
            ["path"] = path,
        };
        Write(record);
    }

    // Diff is bewust plat: gepunte pad → {from, to}. Dat leest achteraf beter
    // dan een boom en past in Discord/kliphistorie zonder verrassingen. Alleen
    // gewijzigd/toegevoegd/verwijderd; ongewijzigd wordt weggelaten.
    static JsonObject BuildDiff(ConfigDocument prev, ConfigDocument now)
    {
        var diff = new JsonObject();

        if (prev.DefaultEntryCap != now.DefaultEntryCap)
            diff["defaults.caps.entries_per_day"] = FromTo(prev.DefaultEntryCap, now.DefaultEntryCap);

        var prevKeys = new HashSet<string>(prev.Accounts.Keys, StringComparer.OrdinalIgnoreCase);
        var nowKeys = new HashSet<string>(now.Accounts.Keys, StringComparer.OrdinalIgnoreCase);

        foreach (var added in nowKeys.Except(prevKeys, StringComparer.OrdinalIgnoreCase))
            diff[$"accounts.{added}"] = FromToStr(null, "added");
        foreach (var removed in prevKeys.Except(nowKeys, StringComparer.OrdinalIgnoreCase))
            diff[$"accounts.{removed}"] = FromToStr("removed", null);

        foreach (var acct in prevKeys.Intersect(nowKeys, StringComparer.OrdinalIgnoreCase))
        {
            var p = prev.Accounts[acct];
            var n = now.Accounts[acct];
            if (!string.Equals(p.Status, n.Status, StringComparison.OrdinalIgnoreCase))
                diff[$"accounts.{acct}.status"] = FromToStr(p.Status, n.Status);
            if (p.DailyEntryCap != n.DailyEntryCap)
                diff[$"accounts.{acct}.caps.entries_per_day"] = FromTo(p.DailyEntryCap, n.DailyEntryCap);
            if (p.Contracts != n.Contracts)
                diff[$"accounts.{acct}.contracts"] = FromTo(p.Contracts, n.Contracts);
        }

        return diff;
    }

    static JsonObject FromTo(int? from, int? to)
    {
        var o = new JsonObject();
        o["from"] = from is int f ? JsonValue.Create(f) : null;
        o["to"] = to is int t ? JsonValue.Create(t) : null;
        return o;
    }

    static JsonObject FromToStr(string? from, string? to)
    {
        var o = new JsonObject();
        o["from"] = from is null ? null : JsonValue.Create(from);
        o["to"] = to is null ? null : JsonValue.Create(to);
        return o;
    }

    static void Write(JsonObject record)
    {
        var path = Path;
        var dir = System.IO.Path.GetDirectoryName(path);
        if (!string.IsNullOrEmpty(dir)) Directory.CreateDirectory(dir);
        var line = record.ToJsonString() + "\n";
        lock (_writeLock)
        {
            File.AppendAllText(path, line);
        }
    }
}
