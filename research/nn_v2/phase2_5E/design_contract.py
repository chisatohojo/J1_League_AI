"""Pure design/negative-control functions. No executable permit or HTTP API.

Positive synthetic checks never authorize evidence acquisition or admission.
Existing Phase 2.5C axis definitions remain authoritative.
"""
from datetime import datetime, timedelta
import hashlib
import json
from pathlib import PureWindowsPath
import re
from urllib.parse import urlsplit

CAPS = {'A': 4, 'B': 2}
BYTE_CAPS = {'A': 2 * 65536 + 2 * 1048576, 'B': 2 * 2097152}
UA = 'J1AI-Research-Timing-Pilot/1.0'


class DesignStop(ValueError):
    pass


def require(ok, reason):
    if not ok:
        raise DesignStop(reason)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def utc(value):
    try:
        require(type(value) is str and 'T' in value, 'UTC_REQUIRED')
        stamp = datetime.fromisoformat(value)
    except (ValueError, TypeError) as exc:
        raise DesignStop('UTC_REQUIRED') from exc
    require(stamp.utcoffset() == timedelta(0), 'UTC_REQUIRED')
    return stamp


def url_parts(value):
    require(type(value) is str and value.isascii() and value == value.strip()
        and not re.search(r'[\x00-\x20\\]', value), 'UNSAFE_URL')
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError as exc:
        raise DesignStop('MALFORMED_URL') from exc
    require(parsed.scheme == 'https' and parsed.hostname and not parsed.username and not parsed.password
        and not parsed.fragment and port in (None, 443), 'HTTPS_ORIGIN_REQUIRED')
    return dict(scheme=parsed.scheme, hostname=parsed.hostname, port=443,
        explicit_port=port, path=parsed.path, query=parsed.query, literal=value)


def exact_target(value, rows):
    parts = url_parts(value)
    matches = [r for r in rows if r.get('url') == value]
    require(len(matches) == 1, 'EXACT_URL_NOT_FIXED_OR_DUPLICATED')
    row = matches[0]
    require(row['hostname'] == parts['hostname'] and row['method'] == 'GET', 'HOST_METHOD_BINDING')
    require(row.get('fixed_for_simulation') is True, 'UNCONFIRMED_TARGET')
    return row


def inspect_synthetic_request(request, design, *, now):
    require(design.get('kind') == 'SYNTHETIC_POLICY_TEST' and request.get('scope') == 'SYNTHETIC_ONLY',
        'NO_EXECUTABLE_PERMIT_IN_THIS_PHASE')
    require(design.get('approved_for_simulation') is True, 'UNAPPROVED_SIMULATION')
    require(utc(now) < utc(design['expires_UTC']), 'EXPIRED_SIMULATION')
    require(request['source_revision'] == design['source_revision'], 'SOURCE_REVISION_MISMATCH')
    require(request['method'] == 'GET' and request['user_agent'] == UA, 'METHOD_AGENT')
    row = exact_target(request['url'], design['rows'])
    require(row['bucket'] == request['bucket'] and row['bucket'] in CAPS, 'BUCKET_MISMATCH')
    require(design.get('host_review', {}).get(row['hostname']) is True, 'HOST_REVIEW_UNKNOWN')
    require(not request.get('Cookie') and not request.get('Authorization'), 'AUTH_COOKIE_FORBIDDEN')
    if row['bucket'] == 'B':
        require(design.get('access_conditions_verified') is True, 'ACCESS_CONDITIONS_UNKNOWN')
    return dict(status='SYNTHETIC_REQUEST_SHAPE_ONLY', row=row,
        execution_authorized=False, permit_issued=False)


def account_attempts(rows):
    """Consume intent even for redirects, retries, errors and uncertain ends."""
    counts = {'A': 0, 'B': 0, 'UNKNOWN': 0}
    sizes = {'A': 0, 'B': 0, 'UNKNOWN': 0}
    for row in rows:
        bucket = row.get('bucket') if row.get('bucket') in CAPS else 'UNKNOWN'
        counts[bucket] += 1
        size = row.get('body_bytes', 0)
        require(type(size) is int and size >= 0, 'INVALID_BODY_SIZE')
        sizes[bucket] += size
    return dict(counts=counts, bytes=sizes, total_attempts=len(rows))


def inspect_budget(rows):
    account = account_attempts(rows)
    reasons = []
    if account['counts']['UNKNOWN']:
        reasons.append('UNKNOWN_BUCKET')
    if account['total_attempts'] > 6:
        reasons.append('GLOBAL_CAP')
    for bucket in CAPS:
        if account['counts'][bucket] > CAPS[bucket]:
            reasons.append('REQUEST_CAP_' + bucket)
        if account['bytes'][bucket] > BYTE_CAPS[bucket]:
            reasons.append('BODY_TOTAL_CAP_' + bucket)
    seen = set()
    last = None
    uncertain = False
    for row in rows:
        if uncertain:
            reasons.append('CONTINUED_AFTER_UNKNOWN_COMPLETION')
        if row.get('reason', 'INITIAL') != 'INITIAL':
            reasons.append('REDIRECT_RETRY_OR_UNKNOWN_ATTEMPT_FORBIDDEN')
        if row['url'] in seen:
            reasons.append('DUPLICATE_URL')
        seen.add(row['url'])
        status = row.get('status')
        if status is None:
            reasons.append('UNKNOWN_STATUS')
        else:
            require(type(status) is int and 100 <= status <= 599, 'INVALID_STATUS')
            if status != 200 and not (status == 404 and row.get('kind') == 'ROBOTS'):
                reasons.append('HTTP_OR_ACCESS_STOP')
        started = utc(row['started_UTC'])
        if last is not None and started < last + timedelta(seconds=5):
            reasons.append('RATE_LIMIT')
        if row.get('completed_UTC') is None:
            reasons.append('UNKNOWN_COMPLETION_CONSUMED')
            uncertain = True
        else:
            last = utc(row['completed_UTC'])
            require(last >= started, 'CLOCK_REVERSAL')
    return dict(account, status='STOP' if reasons else 'SYNTHETIC_ACCOUNTING_ONLY',
        reasons=sorted(set(reasons)), execution_authorized=False)


def inspect_storage_descriptor(desc):
    require(desc.get('scope') == 'SYNTHETIC_ONLY', 'NO_REAL_STORAGE_VALIDATION')
    root, target = desc['root'], desc['path']
    for text in [root, target]:
        require(type(text) is str and re.match(r'^[A-Za-z]:[\\/]', text)
            and not any(part in ('.', '..') for part in re.split(r'[\\/]', text))
            and ':' not in text[2:], 'UNSAFE_STORAGE_PATH')
    base, item = PureWindowsPath(root), PureWindowsPath(target)
    require(item.is_relative_to(base) and item != base, 'OUTSIDE_ALLOWLIST')
    require(desc.get('exclusive_create') is True and desc.get('existing_file') is False, 'NO_CLOBBER')
    require(desc.get('owner_verified') is True and desc.get('DACL_verified') is True
        and desc.get('reparse_clear') is True, 'OWNERSHIP_ACL_REPARSE_UNKNOWN')
    require(desc['root_identity_before'] == desc['root_identity_before_publish'], 'ROOT_REPLACED')
    return dict(status='DESCRIPTOR_SHAPE_ONLY', OS_ACL_proven=False, execution_authorized=False)


def inspect_synthetic_response(raw, metadata_raw, request_raw, pins, design, *, now):
    for body, key in [(raw, 'raw_SHA256'), (metadata_raw, 'metadata_SHA256'), (request_raw, 'request_SHA256')]:
        require(type(body) is bytes and digest(body) == pins[key], 'SEALED_BYTES_MISMATCH')
    request, meta = json.loads(request_raw), json.loads(metadata_raw)
    result = inspect_synthetic_request(request, design, now=now)
    row = result['row']
    require(meta['requested_url'] == meta['final_url'] == request['url'] and meta['redirect_history'] == [], 'REDIRECT_OR_URL_MISMATCH')
    require(meta['request_id'] == request['request_id'] and meta['request_SHA256'] == digest(request_raw)
        and meta['raw_SHA256'] == digest(raw), 'REQUEST_RESPONSE_BINDING')
    require(meta['source_revision'] == request['source_revision'] and meta['bucket'] == request['bucket'], 'REVISION_BUCKET_BINDING')
    require(meta['source_identity'] == request['source_identity'] == row['identity']
        and meta['storage_identity'] == request['storage_identity'], 'SOURCE_STORAGE_IDENTITY')
    inspect_storage_descriptor(meta['storage'])
    require(type(meta['bytes']) is int and meta['bytes'] == len(raw) <= row['body_cap'], 'BODY_CAP_OR_LENGTH')
    require(meta['complete_body'] is True, 'INCOMPLETE_BODY')
    require(meta['automatic_retry'] == meta['redirects_followed'] == 0, 'RETRY_REDIRECT_FORBIDDEN')
    tls = meta['TLS']
    require(tls['verified'] is True and tls['hostname_verified'] is True
        and tls['server_hostname'] == row['hostname'], 'TLS_RECORD_CONTRADICTION')
    require(meta.get('access_control_detected') is False and not meta.get('authentication_required'), 'ACCESS_CONTROL_STOP')
    headers = meta['headers']
    require(isinstance(headers, dict) and all(type(k) is str and type(v) is str for k,v in headers.items()), 'HEADER_SCHEMA')
    require(sum(len(k.encode('utf8')) + len(v.encode('utf8')) + 4 for k,v in headers.items()) <= 32768, 'RESPONSE_HEADERS_CAP')
    require(not any(k.lower() == 'content-encoding' and v.lower() != 'identity' for k,v in headers.items()), 'ENCODING_REQUIRES_REVIEW')
    require(meta['status'] == 200 or row['kind'] == 'ROBOTS' and meta['status'] == 404, 'HTTP_STOP')
    clocks = [utc(meta[k]) for k in ['request_started_UTC', 'response_completed_UTC', 'snapshot_saved_UTC', 'audit_completed_UTC']]
    require(clocks == sorted(clocks) and clocks[0] == utc(request['request_started_UTC']), 'UTC_ORDER_BINDING')
    require(clocks[1]-clocks[0] <= timedelta(seconds=10) and clocks[-1] <= utc(now), 'TIMEOUT_OR_FUTURE_METADATA')
    require(meta.get('first_publication_UTC') is None, 'PUBLICATION_NOT_ESTABLISHED')
    return dict(status='SYNTHETIC_RESPONSE_SHAPE_ONLY', evidence_acquisition_authorized=False,
        site_wide_permission_proven=False, robots_404_not_blanket_permission=meta['status'] == 404,
        A='UNCHANGED', B='HOLD', C='HOLD', D='HOLD', history_admission=False,
        related_fixture_status='UNBOUND_REFERENCE_ONLY', OS_TLS_proven=False)
