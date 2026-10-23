"""Pure validation of an unissued two-document proposal. No transport API."""
from urllib.parse import urlsplit

URLS=(
    'https://www.rfc-editor.org/rfc/rfc9309.html',
    'https://developers.google.com/crawling/docs/robots-txt/robots-txt-spec?hl=ja',
)
IDS=('S1_RFC9309','S2_GOOGLE_ROBOTS_JA')


class ProposalStop(ValueError):
    pass


def require(ok,reason):
    if not ok:raise ProposalStop(reason)


def validate_proposal(value):
    """Success means internally consistent design, never permission to fetch."""
    require(value['kind']=='UNISSUED_OFFICIAL_SPECIFICATION_FETCH_PROPOSAL_V1','PROPOSAL_ONLY')
    require(value['issued'] is False and value['activated'] is False
        and value['permit_id'] is None and value['approval_UTC'] is None
        and value['expires_UTC'] is None,'NO_EXECUTABLE_PERMIT')
    require(type(value['currently_authorized_GET']) is int and value['currently_authorized_GET']==0,'ZERO_AUTHORITY')
    require(value['gate']=='NN_V2_ROBOTS_PARSER_PARTIAL','PARTIAL_REQUIRED')
    require(len(value['documents'])==2,'EXACT_TWO_DOCUMENTS')
    for i,row in enumerate(value['documents']):
        require(row['id']==IDS[i] and row['order']==i+1 and row['URL']==URLS[i],'EXACT_URL_ORDER')
        parsed=urlsplit(row['URL'])
        require(row['scheme']==parsed.scheme=='https' and row['host']==parsed.hostname
            and row['port']==443 and row['explicit_port'] is None and row['path']==parsed.path
            and row['query']==parsed.query and row['fragment']=='','ORIGIN_PATH_QUERY')
        require(row['method']=='GET' and type(row['max_attempts']) is int and row['max_attempts']==1,'GET_ONE_PER_DOCUMENT')
        require(type(row['body_cap_bytes']) is int and row['body_cap_bytes']==2097152,'BODY_CAP')
        require(row['HTTP_status'] is None and row['raw_SHA256'] is None and row['response_verified'] is False,'NO_RESPONSE_CLAIM')
        require(row['candidate_provenance']=='EXPLICIT_USER_SUPPLIED_REFERENCE_URL'
            and row['access_conditions']=='UNKNOWN' and row['execution_authorized'] is False,'NO_IMPLIED_SITE_PERMISSION')
    limits=value['limits']
    expected=dict(max_GET=2,body_total_bytes=4194304,header_bytes_per_response=32768,
        body_plus_header_bytes=4259840,redirect=0,retry=0,parallel=0,
        minimum_interval_after_completion_seconds=5,socket_timeout_seconds=10,
        parent_worker_deadline_seconds=12,cleanup_deadline_seconds=2,whole_run_deadline_seconds=90)
    require(set(limits)==set(expected),'LIMIT_KEYS')
    for k,v in expected.items():require(type(limits[k]) is int and limits[k]==v,'FIXED_LIMIT:'+k)
    require(value['B_GET']==value['A2_A4_GET']==value['extra_robots_GET']==0,'NO_OTHER_TARGET_BUDGET')
    require(value['reuse_G_unused_budget'] is False and value['automatic_source_substitution'] is False,'NO_REUSE_OR_SUBSTITUTION')
    require(value['storage']['created'] is False and value['storage']['absolute_root'] is None
        and value['storage']['exclusive_create_required'] is True,'NO_ACTIVE_STORAGE')
    require(all(value['storage'][k] is True for k in ['raw_SHA256_required','metadata_request_SHA256_required',
        'flush_fsync_readback_required','seal_receipt_required','no_overwrite','private_originals']), 'EVIDENCE_STORAGE_CONTRACT')
    require(value['approval_required'] is True and value['host_access_conditions_review_required'] is True,'FUTURE_APPROVAL_REQUIRED')
    return dict(status='CONSISTENT_UNISSUED_PROPOSAL',currently_authorized_GET=0,
        issued=False,execution_authorized=False,B_authorized=False,history_admission=False)


def validate_review_plan(plan):
    require(plan['kind']=='FUTURE_SOURCE_BOUND_NORMATIVE_REVIEW_CHECKLIST_V1','CHECKLIST_ONLY')
    require(plan['normative_cases_executed']==0 and plan['RFC9309_verified'] is False
        and plan['Google_profile_adopted'] is False,'NO_UNRUN_STANDARDS_TEST_CLAIM')
    require(plan['source_requirement']=='SEALED_ORIGINAL_BYTES_REQUEST_METADATA_RECEIPT_SHA_AND_SECTION_ANCHORS','SOURCE_PROOF_REQUIRED')
    required={'agent_grammar','agent_matching','agent_precedence','group_merge','rule_grammar','longest_rule',
        'allow_tie','wildcard','terminal_anchor','percent_encoding','reserved_octets','unicode','query',
        'unknown_directives','encoding_errors','empty_body','host_scope','HTTP_errors','retrieval_redirect',
        'parse_limits','safety_priority','Google_differences','standard_examples','sealed_A1_replay'}
    rows=plan['items']
    require(len(rows)==len(required) and {r['id'] for r in rows}==required,'CHECKLIST_COVERAGE')
    for row in rows:
        require(row['status']=='PENDING_AUTHORITATIVE_SOURCE' and row['section_anchor'] is None
            and row['normative_expected_result'] is None,'NO_GUESSED_NORMATIVE_RESULT')
        require(row['required_before_offline_verified'] is True,'NO_SILENTLY_WAIVED_GATE')
    return dict(status='PREPARED_NOT_EXECUTED',normative_cases_executed=0,conformance_claim=False)
