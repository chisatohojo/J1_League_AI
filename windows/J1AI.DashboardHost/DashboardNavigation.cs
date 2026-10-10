namespace J1AI.DashboardHost;

internal sealed class DashboardNavigation
{
    internal static readonly string[] Routes = ["/", "/index.html", "/styles.css", "/app.js",
        "/components/prediction-probability-bar.js", "/dashboard-data.js", "/team-colors.js", "/demo-data.js", "/api/dashboard"];
    internal string Origin { get; }
    private readonly Uri origin;
    internal DashboardNavigation(string url)
    {
        origin = new Uri(Readiness.ValidateUrl(url));
        Origin = origin.GetLeftPart(UriPartial.Authority);
    }
    internal bool Allows(string url, bool document)
    {
        if (url.Any(c => char.IsWhiteSpace(c) || char.IsControl(c) || c is '\\' or '%') ||
            !Uri.TryCreate(url, UriKind.Absolute, out var uri) || uri.Scheme != "http" ||
            uri.Host != "127.0.0.1" || uri.Port != origin.Port || uri.UserInfo != "") return false;
        // Parsed scheme/host/port above are authoritative. Also require the raw
        // authority to be canonical (reject numeric IP aliases and leading zeros).
        var authority = System.Text.RegularExpressions.Regex.Match(url, @"\Ahttp://([^/?#]+)/");
        if (!authority.Success || authority.Groups[1].Value != origin.Authority) return false;
        if (!Routes.Contains(uri.AbsolutePath, StringComparer.Ordinal)) return false;
        if (uri.Query != "" && !(uri.AbsolutePath == "/" && uri.Query == "?demo=1" && document)) return false;
        if (document) return uri.AbsolutePath is "/" or "/index.html";
        return uri.Fragment == "" && uri.Query == "";
    }
    internal string ContentSecurityPolicy => $"default-src 'none'; script-src {Origin}; " +
        $"style-src {Origin} 'unsafe-inline'; connect-src {Origin}; img-src data:; " +
        "frame-src 'none'; worker-src 'none'; object-src 'none'; base-uri 'none'; form-action 'none'; " +
        "sandbox allow-scripts allow-same-origin";
}
