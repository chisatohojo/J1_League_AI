using System.Net;
using System.Net.Sockets;

namespace J1AI.SmokeNetworkObserver;

public enum Result { PASS_OBSERVED_SCOPE, BLOCKED, INCONCLUSIVE }
public enum Phase { READY, OBSERVING, NORMAL_END, UNAUTHORIZED, OWNERSHIP_UNKNOWN, WRITE_FAILED, GAP, CRASH }
public enum Disposition { Allowed, Denied, Unknown, NotConnection }
public sealed record ProcessKey(int Pid, long CreatedFileTime)
{ public DateTime CreatedUtc => DateTime.FromFileTimeUtc(CreatedFileTime); }
public sealed record ProcessFact(ProcessKey Key, int ParentPid, string Executable, string[] Arguments, bool HandleVerified);
public sealed record TcpRow(int Pid, long? CreatedFileTime, string? LocalAddress, int? LocalPort,
    string? RemoteAddress, int? RemotePort, string State, int AddressFamily, string? NativeRowHex = null);
public sealed record Endpoint(string Address, int Port, ProcessKey Owner);
public sealed record Decision(Disposition Disposition, string Category, string Reason,
    string? NormalizedAddress = null, long? ScopeId = null, string? TransportMeaning = null);
public sealed record Ownership(ProcessKey[] Runtime, ProcessKey[] Backend, ProcessKey? Worker, string[] Errors);
public sealed record Snapshot(long Sequence, DateTimeOffset QueryStartUtc, DateTimeOffset QueryEndUtc,
    double MonotonicStartMs, double MonotonicEndMs, ProcessFact[] Processes, TcpRow[] Rows,
    string[] CollectionErrors, bool EndConfirmed, string? Run, bool RuntimeEventConfirmed, ProcessKey[]? ConfirmedExited = null);
// This is the only serialized raw type: no command lines, unrelated sockets or user paths.
public sealed record RawSnapshot(long Sequence, DateTimeOffset QueryStartUtc, DateTimeOffset QueryEndUtc,
    double IntervalMs, double DurationMs, bool Gap, ProcessKey[] ObservedRuntime,
    ProcessKey[] Started, ProcessKey[] Absent, ProcessKey[] ConfirmedExited, TcpRow[] Rows, string[] Errors, string Ownership,
    bool RuntimeEventConfirmed);
public sealed record SnapshotVerdict(long Sequence, Endpoint? Backend, Decision[] Decisions,
    Phase Phase, string[] Reasons);
public sealed record Summary(Result Result, Phase Phase, long Snapshots, string Scope, string[] Reasons,
    bool StopRequested, bool StopAcknowledged, bool RuntimeEndConfirmed);

public interface IEvidence
{
    // A successful return MUST mean write + durable flush + read-back equality.
    void SaveVerified(string name, object value);
}
public interface IStop { Task<bool> RequestAsync(string identity, TimeSpan timeout); }
public interface ICollector : IDisposable { Task<Snapshot> CollectAsync(long sequence, CancellationToken token); }

public static class AddressRules
{
    public static (IPAddress? Address, string Category) Parse(string? raw)
    {
        if (string.IsNullOrEmpty(raw)) return (null, "MissingAddress");
        if (raw != raw.Trim() || !IPAddress.TryParse(raw, out var address)) return (null, "InvalidAddress");
        // TryParse accepts octal/hex/short IPv4. Those are never an authorization spelling.
        if (address.AddressFamily == AddressFamily.InterNetwork && address.ToString() != raw)
            return (null, "NonCanonicalIPv4");
        if (address.IsIPv4MappedToIPv6)
        {
            string suffix = raw[(raw.LastIndexOf(':') + 1)..];
            if (suffix.Contains('.') && (!IPAddress.TryParse(suffix, out var v4) || v4.ToString() != suffix))
                return (null, "NonCanonicalIPv4");
            address = address.MapToIPv4();
        }
        byte[] b = address.GetAddressBytes();
        if (b.All(value => value == 0)) return (address, "Unspecified");
        // Scope is retained for endpoint equality/evidence, but does not change
        // the address range. In particular ::1%N is still a loopback range.
        if (IPAddress.IsLoopback(new IPAddress(b))) return (address, "Loopback");
        if (b.Length == 4)
        {
            if (b[0] == 10 || b[0] == 172 && b[1] is >= 16 and <= 31 || b[0] == 192 && b[1] == 168)
                return (address, "PrivateIPv4");
            if (b[0] == 169 && b[1] == 254) return (address, "LinkLocal");
            if (b[0] >= 224 || b[0] == 0) return (address, "ReservedOrMulticast");
        }
        else
        {
            if (address.IsIPv6LinkLocal) return (address, "LinkLocal");
            if ((b[0] & 0xfe) == 0xfc) return (address, "ULA");
            if (address.IsIPv6Multicast) return (address, "ReservedOrMulticast");
        }
        return (address, "Public");
    }

    public static Decision Classify(TcpRow row, Endpoint? backend)
    {
        string meaning = row.State switch
        {
            "LISTEN" => "Listener; not outbound connection evidence",
            "BOUND" or "CLOSED" => "Bound/closed; not established evidence",
            "SYN_SENT" or "SYN_RECEIVED" => "Connection attempt; no payload proof",
            "ESTABLISHED" => "TCP established; no application payload proof",
            "FIN_WAIT1" or "FIN_WAIT2" or "CLOSE_WAIT" or "CLOSING" or "LAST_ACK" or "TIME_WAIT" or "DELETE_TCB"
                => "Closing; no application payload proof",
            _ => "Unknown TCP state"
        };
        Decision D(Disposition d, string cat, string why, IPAddress? ip = null) =>
            new(d, cat, why, ip?.ToString(), ip?.AddressFamily == AddressFamily.InterNetworkV6 ? ip.ScopeId : null, meaning);
        if (row.CreatedFileTime == null) return D(Disposition.Unknown, "OwnershipUnknown", "birth_missing");
        var local = Parse(row.LocalAddress);
        if (local.Address == null || row.LocalPort is not (> 0 and <= 65535) ||
            row.AddressFamily is not (2 or 23)) return D(Disposition.Unknown, "MissingEvidence", "local_endpoint_invalid");
        if (row.State is "LISTEN" or "BOUND" or "CLOSED")
            return D(Disposition.Unknown, "NonConnectionSocket", "unapproved_runtime_listener_or_bound_socket");
        if (meaning == "Unknown TCP state") return D(Disposition.Unknown, "MissingEvidence", "state_unknown");
        var remote = Parse(row.RemoteAddress);
        if (remote.Address == null) return D(Disposition.Unknown, remote.Category, "remote_address_invalid");
        if (remote.Category == "Unspecified" || row.RemotePort is not (> 0 and <= 65535))
            return D(Disposition.Unknown, remote.Category, "remote_endpoint_missing", remote.Address);
        if (backend == null) return D(Disposition.Unknown, "BackendUnknown", "verified_backend_unavailable", remote.Address);
        var approved = Parse(backend.Address);
        if (approved.Category != "Loopback" || backend.Port is not (> 0 and <= 65535))
            return D(Disposition.Unknown, "BackendUnknown", "verified_backend_invalid", remote.Address);
        if (remote.Address.Equals(approved.Address) && row.RemotePort == backend.Port && local.Category == "Loopback")
            return D(Disposition.Allowed, "ApprovedBackend", "exact_verified_address_and_dynamic_port", remote.Address);
        return D(Disposition.Denied, remote.Category == "Loopback" ? "OtherLoopback" : remote.Category,
            "endpoint_not_approved", remote.Address);
    }
}
