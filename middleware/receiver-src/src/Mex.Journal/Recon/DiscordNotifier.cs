using System.Net.Http.Json;
namespace Mex.Journal.Recon;

/// <summary>Post de dagelijkse digest naar Discord. Webhook-URL komt uit een env-var
/// (secret blijft buiten code/config, conform MEX-regel). Zonder env-var: stil overslaan.</summary>
public static class DiscordNotifier
{
    public static async Task<bool> PostAsync(string envVar, string title, string description, int color)
    {
        var url = Environment.GetEnvironmentVariable(envVar);
        if (string.IsNullOrWhiteSpace(url)) return false;
        using var http = new HttpClient();
        var payload = new { embeds = new[] { new { title, description, color } } };
        var resp = await http.PostAsJsonAsync(url, payload);
        return resp.IsSuccessStatusCode;
    }
}
