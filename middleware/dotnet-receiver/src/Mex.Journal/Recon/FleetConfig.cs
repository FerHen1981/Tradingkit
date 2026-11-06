using System.Text.Json;
namespace Mex.Journal.Recon;

/// <summary>fleet-config.json: verwachte accounts + meta. De compleetheids-check
/// (les van 7 aug: PA019 ontbrak stilletjes) schreeuwt als een account géén exports levert.</summary>
public class FleetConfig
{
    public List<string> ExpectedAccounts { get; set; } = new();
    public string? DiscordWebhookEnvVar { get; set; } = "MEX_DISCORD_WEBHOOK";

    public static FleetConfig Load(string? path)
    {
        if (path == null || !File.Exists(path)) return new FleetConfig();
        return JsonSerializer.Deserialize<FleetConfig>(File.ReadAllText(path)) ?? new FleetConfig();
    }
}
