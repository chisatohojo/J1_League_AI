using J1AI.SmokeCoordination;

namespace J1AI.SmokeNetworkObserver;

// The same backend/peer-to-grant decision is used by the pipe adapter and Fakes.
internal sealed class CoordinationDriver(CoordinationSession session, IdentityContract contract)
{
    internal void Update(Snapshot snapshot, ProcessKey connectedWorker, int workerPort, Action<int, string> grant)
    {
        if (workerPort == 0 || session.Aborted || session.Phase is CoordinationPhase.Stopping or CoordinationPhase.Ended) return;
        var owner = OwnershipRules.Resolve(snapshot.Processes, contract);
        CoordinationSession.Require(owner.Worker == connectedWorker && owner.Errors.Length == 0, "coord_worker_peer_unverified");
        var endpoint = OwnershipRules.DiscoverBackend(snapshot.Rows, owner);
        session.Backend(endpoint == null ? null : new(endpoint.Address, endpoint.Port, endpoint.Owner.Pid, endpoint.Owner.CreatedFileTime));
        CoordinationSession.Require(endpoint?.Port == workerPort, "coord_backend_url_mismatch");
        if (session.Phase == CoordinationPhase.Armed)
        {
            string permit = session.Permit(new(endpoint!.Address, endpoint.Port, endpoint.Owner.Pid, endpoint.Owner.CreatedFileTime));
            grant(endpoint.Port, permit);
        }
    }
}
