using System.Net;

namespace J1AI.DashboardHost;

internal sealed record HtmlResponse(byte[] Bytes, string Headers)
{
    private static readonly HashSet<string> HopHeaders = new(StringComparer.OrdinalIgnoreCase)
    { "Connection", "Keep-Alive", "Proxy-Authenticate", "Proxy-Authorization", "TE", "Trailer", "Transfer-Encoding", "Upgrade" };

    // Only an already validated HTML document GET. Never fetch a caller-supplied
    // external URL or /api/dashboard; JSON remains a direct browser/server flow.
    internal static async Task<HtmlResponse> FetchAsync(HttpClient client, DashboardNavigation policy,
        string url, CancellationToken token)
    {
        if (!policy.Allows(url, document: true)) throw new HostError(EventCode.InvalidUrl);
        using var request = new HttpRequestMessage(HttpMethod.Get, url);
        using var response = await client.SendAsync(request, HttpCompletionOption.ResponseHeadersRead, token);
        if (response.StatusCode != HttpStatusCode.OK ||
            response.Content.Headers.ContentType?.MediaType != "text/html" ||
            response.Content.Headers.ContentLength > Readiness.MaxBytes) throw new HostError(EventCode.InvalidResponse);
        using var source = await response.Content.ReadAsStreamAsync(token);
        using var memory = new MemoryStream();
        byte[] buffer = new byte[8192];
        int count;
        while ((count = await source.ReadAsync(buffer, token)) != 0)
        {
            if (memory.Length + count > Readiness.MaxBytes) throw new HostError(EventCode.InvalidResponse);
            memory.Write(buffer, 0, count);
        }
        // End-to-end response headers and exact (possibly encoded) entity bytes
        // are retained. Hop-by-hop transport headers do not apply to this response.
        var headers = response.Headers.Concat(response.Content.Headers)
            .Where(h => !HopHeaders.Contains(h.Key))
            .Select(h => h.Key + ": " + string.Join(", ", h.Value)).ToList();
        headers.Add("Content-Security-Policy: " + policy.ContentSecurityPolicy);
        headers.Add("Cache-Control: no-store");
        return new(memory.ToArray(), string.Join("\r\n", headers));
    }
}
