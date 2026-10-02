// D-82 · Config-API — de HTTP-poort waarmee de (latere) settings-tab de
// configuratie leest en schrijft. Fase 2 van het herijkingsplan.
//
// Ontwerpregel Ferry 27-09: *"authenticatie als ontwerpeis, niet als bijzaak
// — dit scherm stuurt orders."* Één sterke sessie volstaat vandaag (alleen
// Ferry), maar we hebben het zo gebouwd dat een tweede gebruiker later
// zonder herbouw kan bijkomen: de token-map draagt naam → token, en de
// gebruikersnaam belandt in `updated_by` in het auditspoor van D-81.
//
// Endpoints (in `Program.cs` gemount):
//   GET  /api/config          → rauwe file-inhoud + huidige versie
//   PUT  /api/config          → volledige vervanging, gaat door dezelfde
//                                validatie als een file-edit (D-80) en het
//                                auditspoor (D-81). Server overschrijft
//                                `version`, `updated`, `updated_by` — geen
//                                client kan die vervalsen.
//
// Wat dit NIET is:
//   ✘ PATCH — voorlopig alleen volledige vervanging (fase 2 hoeft niet meer)
//   ✘ audit-viewer-endpoint — dat is D-83/D-84 (Web) en leest audit.log
//     rechtstreeks; geen extra API hier tot dat scherm er is
//   ✘ token-management via HTTP — tokens blijven env-var, roteren via de
//     systemd-unit (D-11 blijft het pad)
//
// Auth:
//   MEX_CONFIG_API_TOKENS = "ferry:t0k3nA,operator:t0k3nB"   (aanbevolen)
//   MEX_CONFIG_API_TOKEN  = "single-token"                    (kort, één user)
//   MEX_CONFIG_API_USER   = "ferry"                            (naam bij het single-token)
// Bij geen enkele van deze env-vars: **de endpoints staan dicht** — 401
// terug op elke request. Locked by default is hier de veilige stand.
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;

namespace Mex.Journal.Receiver;

public static class ConfigApi
{
    // --------------------------------------------------------------
    // Auth
    // --------------------------------------------------------------

    /// <summary>Zoekt een `Authorization: Bearer <token>` header en matcht
    /// hem constant-tijd tegen de geconfigureerde tokens. Retourneert de
    /// naam van de user als er een match is, anders `null`.</summary>
    public static string? AuthorizeBearer(string? authorizationHeader)
    {
        if (string.IsNullOrWhiteSpace(authorizationHeader)) return null;
        const string prefix = "Bearer ";
        if (!authorizationHeader.StartsWith(prefix, StringComparison.OrdinalIgnoreCase))
            return null;
        var token = authorizationHeader[prefix.Length..].Trim();
        if (token.Length == 0) return null;

        foreach (var (name, expected) in LoadTokens())
        {
            if (ConstantTimeEquals(expected, token))
                return name;
        }
        return null;
    }

    static IEnumerable<(string Name, string Token)> LoadTokens()
    {
        var multi = Environment.GetEnvironmentVariable("MEX_CONFIG_API_TOKENS") ?? "";
        foreach (var part in multi.Split(',', StringSplitOptions.RemoveEmptyEntries))
        {
            var kv = part.Split(':', 2);
            if (kv.Length == 2 && kv[0].Trim().Length > 0 && kv[1].Trim().Length > 0)
                yield return (kv[0].Trim(), kv[1].Trim());
        }
        var single = Environment.GetEnvironmentVariable("MEX_CONFIG_API_TOKEN");
        if (!string.IsNullOrWhiteSpace(single))
        {
            var user = Environment.GetEnvironmentVariable("MEX_CONFIG_API_USER");
            if (string.IsNullOrWhiteSpace(user)) user = "admin";
            yield return (user, single);
        }
    }

    // Vergelijk twee strings zonder timing-lek. Dit is auth-materiaal, dus
    // een naive `==` verklapt met een enkele microseconde welke prefix
    // klopt en welke niet.
    static bool ConstantTimeEquals(string a, string b)
    {
        var ba = Encoding.UTF8.GetBytes(a);
        var bb = Encoding.UTF8.GetBytes(b);
        // Pad naar gelijke lengte zodat de vergelijking niet lekt op
        // lengte-verschil.
        var len = Math.Max(ba.Length, bb.Length);
        var pa = new byte[len];
        var pb = new byte[len];
        Buffer.BlockCopy(ba, 0, pa, 0, ba.Length);
        Buffer.BlockCopy(bb, 0, pb, 0, bb.Length);
        var eq = CryptographicOperations.FixedTimeEquals(pa, pb);
        // Ook lengte-mismatch als fail markeren.
        return eq && ba.Length == bb.Length;
    }

    // --------------------------------------------------------------
    // GET
    // --------------------------------------------------------------

    /// <summary>Payload van GET /api/config. Geeft de rauwe file terug (of
    /// een leeg object als er nog geen file is) plus de huidige effectieve
    /// versie zoals de provider hem draagt. `path` en `updated_at` helpen de
    /// client zien of ze met dezelfde bron praten.</summary>
    public static JsonObject BuildGetResponse()
    {
        var raw = ConfigProvider.ReadRawOrNull();
        JsonNode? fileNode = null;
        if (raw is not null)
        {
            try { fileNode = JsonNode.Parse(raw); }
            catch { fileNode = null; }
        }
        return new JsonObject
        {
            ["path"] = ConfigProvider.Path,
            ["active_version"] = ConfigProvider.Current.Version,
            ["active_updated_at"] = ConfigProvider.Current.UpdatedAt,
            ["file_present"] = raw is not null,
            ["file"] = fileNode ?? (JsonNode)new JsonObject(),
        };
    }

    // --------------------------------------------------------------
    // PUT
    // --------------------------------------------------------------

    public sealed class WriteResult
    {
        public bool Ok { get; init; }
        public int? Version { get; init; }
        public string Error { get; init; } = "";

        public static WriteResult Success(int version) =>
            new() { Ok = true, Version = version };
        public static WriteResult Fail(string reason) =>
            new() { Ok = false, Error = reason };
    }

    // Serialiseer schrijfacties. Vandaag is er één gebruiker, morgen kunnen
    // het er twee zijn (Ferry's uitbreidingseis). Zonder deze lock kunnen
    // twee gelijktijdige PUTs allebei versienummer N+1 nemen, waarna één
    // van beide stil verdwijnt.
    static readonly SemaphoreSlim _writeGate = new(1, 1);

    /// <summary>PUT /api/config — vervangt de configuratie volledig. Doet
    /// **eerst** validatie tegen ConfigValidator, dan pas een atomaire write
    /// (tmp + rename), dan ForceReload zodat het antwoord al de nieuwe
    /// versie draagt. Server-side metadata (`version`, `updated`,
    /// `updated_by`) wordt door de server gezet — een client kan die niet
    /// vervalsen.</summary>
    public static async Task<WriteResult> WriteAsync(string body, string user)
    {
        await _writeGate.WaitAsync();
        try
        {
            return await WriteInternalAsync(body, user);
        }
        finally
        {
            _writeGate.Release();
        }
    }

    // --------------------------------------------------------------
    // D-82-completion · Dry-run validatie. Board-entry noemt letterlijk
    // "lezen, valideren, schrijven" — dit is de tweede werkwoord. De
    // settings-tab kan hiermee een concept tonen zonder dat er iets op
    // disk terechtkomt of een auditregel wordt geschreven.
    // --------------------------------------------------------------

    public static (bool Ok, string Error, int ProposedVersion) ValidateOnly(string body)
    {
        JsonNode? root;
        try { root = JsonNode.Parse(body); }
        catch (JsonException ex) { return (false, $"JSON parse: {ex.Message}", 0); }
        if (root is not JsonObject obj)
            return (false, "top-level must be a JSON object", 0);

        // We spelen dezelfde server-side-overschrijvingen na als in WriteAsync
        // zodat de client dezelfde validatie krijgt die live zou draaien.
        var nextVersion = ConfigProvider.Current.Version + 1;
        obj["version"] = nextVersion;
        obj["updated"] = DateTime.UtcNow.ToString("o");
        obj["updated_by"] = "validate-only";

        var normalized = obj.ToJsonString();
        var (ok, reason) = ConfigProvider.TryParseAndValidate(normalized);
        return (ok, reason, nextVersion);
    }

    // --------------------------------------------------------------
    // D-82-completion · Audit-log leesbaarheid. Web moet een history-
    // paneel kunnen tonen ("wie/wat/wanneer, laatste 50"). We lezen
    // rechtstreeks van disk zodat we geen state hoeven bij te houden;
    // het bestand is append-only (D-81) en tail-N is een goedkope
    // operatie.
    // --------------------------------------------------------------

    public static JsonObject BuildAuditResponse(int limit)
    {
        var path = Environment.GetEnvironmentVariable("MEX_CONFIG_AUDIT_PATH")
            ?? "/root/mex-config/audit.log";
        var entries = new JsonArray();
        int total = 0;

        if (File.Exists(path))
        {
            // ReadAllLines op een groeiend bestand is fine — audit.log
            // is één JSON-regel per gebeurtenis en groeit niet gigabyte-
            // groot. Als het ooit een issue wordt: reverse-read met
            // fixed buffer. Vandaag over-engineering.
            var lines = File.ReadAllLines(path);
            total = lines.Length;
            var take = Math.Clamp(limit, 1, 500);
            var start = Math.Max(0, total - take);
            for (var i = start; i < total; i++)
            {
                var line = lines[i];
                if (string.IsNullOrWhiteSpace(line)) continue;
                try
                {
                    var node = JsonNode.Parse(line);
                    if (node is not null) entries.Add(node);
                }
                catch
                {
                    // Kapotte regel? Ignore — audit-lezen mag nooit
                    // faalgeschrei geven; het scherm toont wat er is.
                }
            }
        }

        return new JsonObject
        {
            ["path"] = path,
            ["total"] = total,
            ["returned"] = entries.Count,
            ["entries"] = entries,
        };
    }

    // --------------------------------------------------------------
    // D-85 · Secrets-endpoints. Namen worden geretourneerd, waarden nooit.
    // De GET is bewust minimalistisch (naam + last_written_utc) zodat de
    // settings-tab kan tonen *"apex_pmt · ✓ gezet · laatst gewijzigd 12-09"*
    // zonder ooit een waarde te ontvangen.
    // --------------------------------------------------------------

    public static JsonObject BuildSecretsListResponse()
    {
        var meta = SecretsStore.ListMetadata();
        var arr = new JsonArray();
        foreach (var m in meta)
        {
            arr.Add(new JsonObject
            {
                ["name"] = m.Name,
                ["last_written_utc"] =
                    m.LastWrittenUtc == default ? null : m.LastWrittenUtc.ToString("o"),
            });
        }
        return new JsonObject
        {
            ["path"] = SecretsStore.Path,
            ["count"] = meta.Count,
            ["secrets"] = arr,
        };
    }

    /// <summary>PUT /api/secrets/{name} — schrijft één geheim. Body-vorm:
    /// `{"value": "<string>"}`. Lege of ontbrekende `value` wist het geheim
    /// (DELETE-semantiek). Naam mag geen slashes bevatten — dat is een
    /// URL-veiligheidscheck; de kluis staat het toe, maar het is een teken
    /// van een bug bij de aanroeper.</summary>
    public static async Task<WriteResult> WriteSecretAsync(string name, string body, string user)
    {
        if (string.IsNullOrEmpty(name) || name.Contains('/') || name.Contains(".."))
            return WriteResult.Fail("invalid secret name");

        string? value = null;
        if (!string.IsNullOrWhiteSpace(body))
        {
            JsonNode? root;
            try { root = JsonNode.Parse(body); }
            catch (JsonException ex) { return WriteResult.Fail($"JSON parse: {ex.Message}"); }
            if (root is not JsonObject obj)
                return WriteResult.Fail("top-level must be a JSON object");
            value = obj["value"]?.ToString();
        }

        try
        {
            await SecretsStore.WriteAsync(name, value);
        }
        catch (Exception ex)
        {
            return WriteResult.Fail($"write failed: {ex.Message}");
        }
        // De version-teller is een config-concept, niet een secrets-concept —
        // geheimen hebben geen monotonisch stijgend versienummer nodig omdat
        // ze niet worden doorgereden naar de gates. Return 0 zodat het contract
        // van WriteResult past.
        return WriteResult.Success(0);
    }

    static async Task<WriteResult> WriteInternalAsync(string body, string user)
    {
        JsonNode? root;
        try { root = JsonNode.Parse(body); }
        catch (JsonException ex) { return WriteResult.Fail($"JSON parse: {ex.Message}"); }
        if (root is not JsonObject obj)
            return WriteResult.Fail("top-level must be a JSON object");

        // Server-side metadata — client mag deze in de body meesturen
        // maar wij overschrijven ze. Zo blijft `updated_by` de waarheid en
        // is `version` monotonisch stijgend.
        var nextVersion = ConfigProvider.Current.Version + 1;
        obj["version"] = nextVersion;
        obj["updated"] = DateTime.UtcNow.ToString("o");
        obj["updated_by"] = user;

        var normalized = obj.ToJsonString(new JsonSerializerOptions
        {
            WriteIndented = true,
        });

        // Validate eerst, schrijf pas als het schoon is. Dit voorkomt dat de
        // gebruiker een file wegschrijft die de 5s-poll straks alsnog
        // rejecteert — de PUT geeft nu directe feedback.
        var (ok, reason) = ConfigProvider.TryParseAndValidate(normalized);
        if (!ok) return WriteResult.Fail(reason);

        var path = ConfigProvider.Path;
        var dir = System.IO.Path.GetDirectoryName(path);
        if (!string.IsNullOrEmpty(dir)) Directory.CreateDirectory(dir);
        var tmp = path + ".tmp";
        await File.WriteAllTextAsync(tmp, normalized);
        // File.Move met overwrite is atomair op POSIX en Windows-NTFS voor
        // een file op dezelfde volume — geen halve staat leesbaar voor de
        // provider.
        File.Move(tmp, path, overwrite: true);

        // Direct herladen zodat het antwoord de nieuwe versie beschrijft en
        // de audit-lijn ergens tussen de PUT-response en de volgende poll
        // zit. Faalt dit onverhoopt, dan pikt de reguliere 5s-poll het op.
        ConfigProvider.ForceReload();

        return WriteResult.Success(nextVersion);
    }
}
