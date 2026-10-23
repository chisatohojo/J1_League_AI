"""Pure discovery safeguards, not B/C/D admission or a fetch implementation.

Authoritative axis definitions remain Phase 2.5C CONTRACT.md. Functions here
inspect candidate provenance and missing evidence only; no model/IO/permit API.
"""
from datetime import datetime
import hashlib
from html.parser import HTMLParser
import re
from urllib.parse import urljoin, urlsplit, urlunsplit

HOSTS = frozenset({'data.j-league.or.jp', 'www.jleague.jp'})
AXES = frozenset({'A', 'B', 'C', 'D'})
ROLES = frozenset({'planned_kickoff', 'actual_kickoff', 'change_announcement',
    'information_publication', 'acquisition', 'prediction_cutoff', 'result_available'})


class DiscoveryStop(ValueError):
    """A contradictory witness/revision, not an ordinary evidence gap."""


def require(value, reason):
    if not value:
        raise DiscoveryStop(reason)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def axes(values):
    require(isinstance(values, (list, tuple)) and bool(values), 'AXIS_LIST_REQUIRED')
    require(all(type(v) is str and v in AXES for v in values), 'UNKNOWN_EVIDENCE_AXIS')
    require(len(values) == len(set(values)), 'DUPLICATE_AXIS')
    return tuple(sorted(values))


def aware(value):
    require(type(value) is str and re.match(r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}', value), 'EXACT_OFFSET_TIME_REQUIRED')
    try:
        dt = datetime.fromisoformat(value)
    except ValueError as exc:
        raise DiscoveryStop('INVALID_CLOCK') from exc
    require(dt.utcoffset() is not None, 'TIMEZONE_REQUIRED')
    return dt


def inspect_time(claim, *, cutoff=None):
    """A well-formed claim is not proof of B/C/D; never infer a missing time."""
    require(claim['role'] in ROLES, 'UNKNOWN_TIME_ROLE')
    reasons = []
    if claim.get('precision') != 'SECOND_WITH_OFFSET':
        reasons.append('DATE_ONLY_OR_UNKNOWN_PRECISION')
    try:
        dt = aware(claim.get('value'))
    except DiscoveryStop:
        dt = None
        reasons.append('MISSING_OR_UNPROVEN_EXACT_TIME')
    permitted = {
        'planned_kickoff': {'SCHEDULE_OBSERVATION'},
        'actual_kickoff': {'OFFICIAL_EXPLICIT_EVENT'},
        'change_announcement': {'OFFICIAL_EXPLICIT_NOTICE'},
        'information_publication': {'OFFICIAL_EXPLICIT_PUBLICATION'},
        'acquisition': {'REQUEST_RESPONSE_COMPLETION'},
        'prediction_cutoff': {'ACTUAL_REGISTERED_CUTOFF'},
        'result_available': {'OFFICIAL_COMPLETED_RESULT_WITNESS'},
    }
    if claim.get('proof_kind') not in permitted[claim['role']]:
        reasons.append('ROLE_NOT_PROVEN_BY_THIS_SOURCE_KIND')
    if claim.get('source_verified') is not True or not re.fullmatch(r'[a-f0-9]{64}', claim.get('raw_sha256', '')):
        reasons.append('MISSING_VERIFIED_ORIGINAL')
    if cutoff is not None and dt is not None and dt > aware(cutoff):
        reasons.append('AFTER_CUTOFF')
    if cutoff is not None:
        try:
            acquired = aware(claim.get('observed_version_acquired_at'))
        except DiscoveryStop:
            reasons.append('NO_ASOF_VERSION_ACQUISITION_PROOF')
        else:
            if acquired > aware(cutoff):
                reasons.append('LATER_ACQUIRED_VERSION_NOT_PAST_PIT_PROOF')
    return dict(status='HOLD' if reasons else 'CLAIM_SHAPE_VERIFIED_ONLY', reasons=reasons,
        evidence_axis_PASS=False, history_admission=False)


def resolve_saved_link(base_url, href):
    """RFC resolution of a literal saved href, never ID/URL generation."""
    base = urlsplit(base_url)
    require(base.scheme == 'https' and base.netloc in HOSTS, 'UNVERIFIED_SOURCE_BASE')
    if not isinstance(href, str) or not href or href != href.strip() or any(ord(ch) < 32 for ch in href) or '\\' in href:
        return dict(url=None, status='REJECTED_UNSAFE_LITERAL', execution_authorized=False)
    value = urljoin(base_url, href)
    parsed = urlsplit(value)
    if parsed.scheme != 'https' or parsed.netloc not in HOSTS:
        return dict(url=value, status='UNAPPROVED_HOST_OR_SCHEME', execution_authorized=False)
    # The GET target for an observed fragment link is the observed resource;
    # retain the full href separately so this is not mistaken for a new URL.
    target = urlunsplit((parsed.scheme, parsed.netloc, parsed.path, parsed.query, ''))
    return dict(url=target, literal_resolved_url=value, status='SAVED_LINK_CANDIDATE_ONLY',
        current_existence='UNKNOWN', historical_publication='UNKNOWN', execution_authorized=False)


class _Links(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links = []
        self.base_tags = []
        self.active = None

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if tag == 'base':
            self.base_tags.append(attributes.get('href'))
        if tag in {'a', 'area', 'link'} and attributes.get('href') is not None:
            entry = dict(href=attributes['href'], tag=tag, source_line=self.getpos()[0],
                source_column=self.getpos()[1], start_tag=self.get_starttag_text(), text='')
            self.links.append(entry)
            if tag == 'a':
                self.active = entry

    def handle_data(self, data):
        if self.active is not None:
            self.active['text'] += data

    def handle_endtag(self, tag):
        if tag == 'a':
            self.active = None


def extract_saved_links(raw, *, expected_sha256, source_url):
    require(type(raw) is bytes and sha(raw) == expected_sha256, 'ORIGINAL_SHA_MISMATCH')
    parser = _Links()
    parser.feed(raw.decode('utf-8-sig'))
    parser.close()
    require(not parser.base_tags or parser.base_tags == [source_url], 'HTML_BASE_REQUIRES_REVIEW')
    rows = []
    for link in parser.links:
        resolved = resolve_saved_link(source_url, link['href'])
        rows.append(dict(link, **resolved, source_raw_sha256=expected_sha256,
            source_url=source_url, origin='LITERAL_SAVED_HTML_ATTRIBUTE',
            tag_sha256=sha(link['start_tag'].encode('utf8'))))
    return rows


def witness_set(rows, *, expected_revision):
    seen = set()
    for row in rows:
        require(row['revision'] == expected_revision, 'SOURCE_REVISION_MISMATCH')
        key = (row['identity'], row['url'], row['raw_sha256'], row['role'])
        require(key not in seen, 'DUPLICATE_WITNESS')
        seen.add(key)
    return len(seen)


def trace_requirements(target, rows, *, expected_prior_identities):
    """Report trace gaps; no features, probabilities or result-event admission."""
    missing = []
    if expected_prior_identities is None:
        missing.append('UNKNOWN_COMPLETE_HISTORY_UNIVERSE')
    if target.get('cutoff') is None:
        missing.append('NO_ACTUAL_PREDICTION_CUTOFF')
    else:
        require(aware(target['cutoff']) < aware(target['kickoff']), 'CUTOFF_NOT_PRE_MATCH')
    if rows is None:
        missing.append('NO_PRIOR_RESULT_TRACE')
        rows = []
    ids = [r['identity'] for r in rows]
    require(target['identity'] not in ids and len(ids) == len(set(ids)), 'SELF_OR_DUPLICATE_HISTORY')
    if expected_prior_identities is not None and set(ids) != set(expected_prior_identities):
        missing.append('INCOMPLETE_OR_EXTRA_HISTORY')
    for row in rows:
        require(row['revision'] == target['revision'], 'SOURCE_REVISION_MISMATCH')
        for key in ['raw_sha256', 'metadata_sha256', 'request_sha256']:
            if not re.fullmatch(r'[a-f0-9]{64}', row.get(key, '')):
                missing.append('MISSING_TRACE_' + key)
        for role in ['actual_kickoff', 'result_available', 'acquisition']:
            claim = row.get(role)
            if claim is None or claim.get('role') != role or inspect_time(claim, cutoff=target.get('cutoff'))['status'] == 'HOLD':
                missing.append('UNPROVEN_TRACE_' + role)
        if row.get('end_time') is None:
            missing.append('UNPROVEN_RESULT_END_TIME')
        else:
            aware(row['end_time'])
        if row.get('actual_kickoff') and row.get('end_time') and row.get('result_available') and row.get('acquisition'):
            try:
                order = [aware(row['actual_kickoff']['value']), aware(row['end_time']),
                    aware(row['result_available']['value']), aware(row['acquisition']['value'])]
            except DiscoveryStop:
                missing.append('UNKNOWN_EVENT_CLOCK_ORDER')
            else:
                require(order == sorted(order), 'EVENT_CLOCK_ORDER_CONTRADICTION')
        if row.get('verified_complete_regulation_result') is not True:
            missing.append('UNVERIFIED_REGULATION_RESULT')
    return dict(status='HOLD' if missing else 'TRACE_FIELDS_COMPLETE_NOT_ADMISSION',
        missing=sorted(set(missing)), D_PASS=False, history_admission=False)


def select_samples(rows, *, blocked_identities, maximum=10):
    require(type(maximum) is int and 0 <= maximum <= 10, 'SAMPLE_LIMIT')
    ids = [r['identity'] for r in rows]
    require(len(ids) == len(set(ids)), 'DUPLICATE_FIXTURE_UNIVERSE')
    available = sorted((r for r in rows if r['identity'] not in blocked_identities), key=lambda r: r['ordinal'])
    selected = []
    groups = [
        ('KICKOFF_NOTATION_DIFFERENCE_CAUSE_UNKNOWN', 4, lambda r: r['notation_difference']),
        ('NO_OBSERVED_CHANGE_MATCH_PAGE_ID_KNOWN', 2, lambda r: not r['notation_difference'] and r['match_page_ID_known']),
        ('PK_SEPARATION_MATCH_PAGE_ID_UNKNOWN', 2, lambda r: r['PK'] and not r['match_page_ID_known']),
        ('NO_OBSERVED_CHANGE_MATCH_PAGE_ID_UNKNOWN', 2, lambda r: not r['notation_difference'] and not r['match_page_ID_known']),
    ]
    for reason, count, predicate in groups:
        pool = [r for r in available if r['identity'] not in {s['identity'] for s in selected} and predicate(r)]
        for row in pool[:min(count, maximum-len(selected))]:
            selected.append(dict(row, selection_reason=reason, actual_schedule_unchanged_proven=False,
                investigation_only=True, evaluation_registration=False, history_admission=False))
    return selected
