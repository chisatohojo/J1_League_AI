"""Pure synthetic design comparison. No I/O, permits, acquisition or admission path."""
FATAL = frozenset({
    "TRANSPORT_ERROR", "HTTP403", "HTTP429", "ACCESS_RESTRICTION", "TIMEOUT",
    "IDENTITY_CONFLICT", "RESULT_CONFLICT", "SHA_MISMATCH", "LIMIT_EXCEEDED",
    "UNKNOWN_TRANSPORT_STATE", "REDIRECT", "TLS_FAILURE",
})
KNOWN = FATAL | {"DETAIL_CHECKS_PASS", "UNKNOWN_REMARK", "UNKNOWN_TIMING_NOTE"}


def simulate(events, *, mode="CURRENT_STOP_ON_ANY_HOLD", cap=4):
    """Compare policies over fabricated event labels; never dispatch a request."""
    if mode not in {"CURRENT_STOP_ON_ANY_HOLD", "PROPOSED_QUARANTINE_ONLY"}:
        raise ValueError("Unknown policy")
    if type(cap) is not int or cap < 1:
        raise ValueError("Invalid cap")
    seen = set()
    records = []
    stop = None
    for token, outcome in events:
        if stop is not None:
            records.append((token, "NOT_STARTED_AFTER_GLOBAL_STOP", False))
            continue
        if token in seen or len(seen) >= cap:
            stop = "DUPLICATE_OR_LIMIT"
        elif outcome not in KNOWN or outcome in FATAL:
            stop = outcome
        elif outcome in {"UNKNOWN_REMARK", "UNKNOWN_TIMING_NOTE"}:
            records.append((token, "QUARANTINED_HOLD", False))
            seen.add(token)
            if mode == "CURRENT_STOP_ON_ANY_HOLD":
                stop = outcome
            continue
        else:
            records.append((token, "DETAIL_A_ONLY", False))
            seen.add(token)
            continue
        records.append((token, "GLOBAL_STOP", False))
    return {"records": records, "stop": stop, "history_admissions": 0,
            "requests_dispatched": 0, "permits_created": 0,
            "connected_to_acquisition": False}
