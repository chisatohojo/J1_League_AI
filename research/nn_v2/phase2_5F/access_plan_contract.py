"""Pure, non-executable A-plan checks and synthetic receipt-prefix checks.

No HTTP client, permit issuer, filesystem writer or acquisition entrypoint.
Candidate endpoints are design choices, never response or permission evidence.
"""
from datetime import datetime, timedelta
from urllib.parse import urlsplit

URLS = (
    'https://www.jleague.jp/robots.txt',
    'https://aboutj.jleague.jp/robots.txt',
    'https://www.jleague.jp/general/kiyaku/',
    'https://www.jleague.jp/general/copyright/',
)
ROLES = ('ROBOTS', 'ROBOTS', 'SITE_TERMS', 'COPYRIGHT_GUIDANCE')
CAPS = (65536, 65536, 1048576, 1048576)
BODY_CAP = sum(CAPS)
HEADER_CAP = 32768


class PlanStop(ValueError):
    pass


def require(condition, reason):
    if not condition:
        raise PlanStop(reason)


def utc(value):
    require(type(value) is str and 'T' in value, 'UTC_REQUIRED')
    try:
        result = datetime.fromisoformat(value)
    except ValueError as exc:
        raise PlanStop('UTC_REQUIRED') from exc
    require(result.utcoffset() == timedelta(0), 'UTC_REQUIRED')
    return result


def inspect_plan(plan):
    """Validate a static design. A positive result grants zero authority."""
    require(plan['kind'] == 'STATIC_A_APPROVAL_PREPARATION_ONLY', 'DESIGN_ONLY')
    require(plan['permit_id'] is None and plan['approval_UTC'] is None, 'NO_PERMIT_OR_APPROVAL')
    require(plan['issued'] is False and plan['activated'] is False
            and type(plan['currently_authorized_requests']) is int
            and plan['currently_authorized_requests'] == 0, 'ZERO_AUTHORITY')
    require(plan['gate'] == 'NN_V2_BCD_PERMIT_DESIGN_PARTIAL', 'UNKNOWN_CONDITIONS_REQUIRE_PARTIAL')
    require(len(plan['candidates']) == 4, 'EXACT_FOUR_CANDIDATES')
    for i, row in enumerate(plan['candidates']):
        require(row['id'] == f'A{i+1}' and row['order'] == i+1, 'FIXED_ORDER')
        require(row['url'] == URLS[i], 'EXACT_LITERAL_URL')
        parsed = urlsplit(row['url'])
        require(row['scheme'] == parsed.scheme == 'https' and row['host'] == parsed.hostname
                and row['port'] == 443 and row['explicit_port'] is None
                and row['path'] == parsed.path and row['query'] == '' and row['fragment'] == '', 'URL_COMPONENTS')
        require(row['bucket'] == 'A' and row['role'] == ROLES[i], 'A_CONDITIONS_ONLY')
        require(row['method'] == 'GET' and row['max_requests'] == 1
                and row['body_cap_bytes'] == CAPS[i] and row['redirect_follow'] == 0, 'ROW_LIMITS')
        require(row['HTTP_status'] is None and row['response_verified'] is False
                and row['content_permission'] == 'UNKNOWN' and row['execution_authorized'] is False, 'NO_RESPONSE_OR_PERMISSION_CLAIM')
    limits = plan['limits']
    for key, expected in dict(max_requests=4, body_bytes=BODY_CAP, header_bytes_per_request=HEADER_CAP,
                              body_plus_header_bytes=BODY_CAP+4*HEADER_CAP, retry=0, parallel=0,
                              redirect_follow=0, interval_after_completion_seconds=5,
                              socket_timeout_seconds=10, parent_worker_deadline_seconds=12,
                              cleanup_deadline_seconds=2, process_deadline_seconds=120).items():
        require(type(limits[key]) is int and limits[key] == expected, 'FIXED_LIMIT:'+key)
    require(plan['B_authorized'] is False and plan['B_requests_in_A'] == 0, 'NO_B_IN_A')
    require(plan['storage']['created'] is False and plan['storage']['exclusive_create_required'] is True
            and plan['storage']['permit_or_worker_created'] is False, 'DESTINATION_NOT_ACTIVATED')
    require(plan['host_findings']['aboutj.jleague.jp']['operator'] == 'UNKNOWN'
            and plan['host_findings']['aboutj.jleague.jp']['terms_applicability'] == 'UNKNOWN', 'ABOUTJ_NOT_PROVEN')
    return dict(static_validation='PASS', gate=plan['gate'], execution_authorized=False,
                B_authorized=False, history_admission=False)


def inspect_synthetic_prefix(plan, receipts):
    """Check synthetic intent accounting, not an executable acquisition policy.

    A timeout/unknown completion consumes the attempt and terminates the prefix.
    Even a robots 404 requires human interpretation before further conditions
    checks. Neither it nor a 200 is a positive site-wide permission decision.
    """
    inspect_plan(plan)
    require(len(receipts) <= 4, 'REQUEST_CAP')
    total = 0
    previous = None
    stopped = False
    for i, receipt in enumerate(receipts):
        require(not stopped, 'CONTINUED_AFTER_STOP')
        require(receipt['scope'] == 'SYNTHETIC_ONLY', 'SYNTHETIC_ONLY')
        require(receipt['url'] == URLS[i] and receipt['id'] == f'A{i+1}', 'NO_REORDER_RETRY_OR_B_URL')
        require(receipt['redirect_follow'] == 0 and receipt['retry'] == 0, 'REDIRECT_OR_RETRY')
        start = utc(receipt['request_started_UTC'])
        if previous:
            require((start-previous).total_seconds() >= 5, 'RATE_OR_CLOCK')
        size = receipt['body_bytes']
        header_size = receipt['header_bytes']
        require(type(size) is int and 0 <= size <= CAPS[i], 'BODY_CAP')
        require(type(header_size) is int and 0 <= header_size <= HEADER_CAP, 'HEADER_CAP')
        total += size
        require(total <= BODY_CAP, 'TOTAL_BODY_CAP')
        end = receipt['response_completed_UTC']
        if end is None:
            stopped = True
        else:
            previous = utc(end)
            require(0 <= (previous-start).total_seconds() <= 10, 'TIMEOUT_OR_CLOCK')
            require((previous-utc(receipts[0]['request_started_UTC'])).total_seconds() <= 120, 'PROCESS_DEADLINE')
            status = receipt['HTTP_status']
            acceptable_response = status == 200 or (i < 2 and status == 404)
            stopped = not (acceptable_response and receipt['TLS_verified'] is True
                           and receipt['access_restriction'] is False
                           and receipt['complete_and_sealed'] is True
                           and receipt['reviewed_for_next_conditions_check'] is True)
    return dict(attempts_consumed=len(receipts), body_bytes=total, stopped=stopped,
                execution_authorized=False, B_authorized=False, content_permission='UNKNOWN',
                B='HOLD', C='HOLD', D='HOLD', history_admission=False)
