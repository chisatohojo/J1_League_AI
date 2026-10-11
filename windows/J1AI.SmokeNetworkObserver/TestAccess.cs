using System.Runtime.CompilerServices;

[assembly: InternalsVisibleTo("J1AI.SmokeNetworkObserver.Tests")]

namespace J1AI.SmokeNetworkObserver;

// Fault seam has no CLI/environment switch and is internal to this assembly.
// Production always constructs the unmodified policy via the public constructor.
internal class ObservationPolicy
{
    internal virtual Decision Classify(TcpRow row, Endpoint? endpoint) => AddressRules.Classify(row, endpoint);
    internal virtual bool Gap(bool detected) => detected;
    internal virtual bool KeyMatches(ProcessKey key, TcpRow row) => key.Pid == row.Pid && key.CreatedFileTime == row.CreatedFileTime;
    internal virtual bool BackendRequired => true;
    internal virtual Task BeforeRaw(IStop stop) => Task.CompletedTask;
}
