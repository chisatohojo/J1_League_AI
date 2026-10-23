"""Synthetic policy descriptors only. No real permit, GET/HEAD/DNS or files."""
from copy import deepcopy
import ast
import importlib.util
import json
from pathlib import Path

import pytest

FILE=Path(__file__).parents[1]/'research/nn_v2/phase2_5E/design_contract.py'
spec=importlib.util.spec_from_file_location('permit_design',FILE)
d=importlib.util.module_from_spec(spec);spec.loader.exec_module(d)
URL='https://www.jleague.jp/synthetic/index/'
NOW='2026-01-02T00:00:10+00:00'


def storage(**changes):
    v=dict(scope='SYNTHETIC_ONLY',root='T:/synthetic-evidence/run',path='T:/synthetic-evidence/run/B/source-0001/raw.bin',
        exclusive_create=True,existing_file=False,owner_verified=True,DACL_verified=True,reparse_clear=True,
        root_identity_before='synthetic-file-id',root_identity_before_publish='synthetic-file-id')
    v.update(changes);return v


def fixture(kind='INDEX'):
    bucket='A' if kind=='ROBOTS' else 'B'
    row=dict(url=URL,hostname='www.jleague.jp',method='GET',bucket=bucket,kind=kind,
        identity='synthetic:index',body_cap=128,fixed_for_simulation=True)
    design=dict(kind='SYNTHETIC_POLICY_TEST',approved_for_simulation=True,expires_UTC='2026-01-03T00:00:00+00:00',
        source_revision='synthetic-fixed-revision',rows=[row],host_review={'www.jleague.jp':True},access_conditions_verified=True)
    request=dict(scope='SYNTHETIC_ONLY',request_id='synthetic-request',url=URL,method='GET',bucket=bucket,
        user_agent=d.UA,source_revision=design['source_revision'],source_identity=row['identity'],
        storage_identity='synthetic-store',request_started_UTC='2026-01-02T00:00:00+00:00')
    raw=b'synthetic body'
    meta=dict(requested_url=URL,final_url=URL,request_id=request['request_id'],bucket=bucket,
        source_revision=design['source_revision'],source_identity=row['identity'],storage_identity=request['storage_identity'],
        request_SHA256='',raw_SHA256=d.digest(raw),bytes=len(raw),complete_body=True,automatic_retry=0,redirects_followed=0,
        redirect_history=[],TLS=dict(verified=True,hostname_verified=True,server_hostname='www.jleague.jp'),
        status=200,headers={'Content-Type':'text/html','Date':'not used as publication time'},
        access_control_detected=False,authentication_required=False,first_publication_UTC=None,storage=storage(),
        request_started_UTC=request['request_started_UTC'],response_completed_UTC='2026-01-02T00:00:01+00:00',
        snapshot_saved_UTC='2026-01-02T00:00:02+00:00',audit_completed_UTC='2026-01-02T00:00:03+00:00')
    return raw,meta,request,design


def seal(raw,meta,request):
    encode=lambda v:json.dumps(v,sort_keys=True).encode()
    req=encode(request);meta['request_SHA256']=d.digest(req);md=encode(meta)
    return raw,md,req,dict(raw_SHA256=d.digest(raw),metadata_SHA256=d.digest(md),request_SHA256=d.digest(req))


def attempt(i=0,**changes):
    v=dict(bucket='B',url=f'https://www.jleague.jp/synthetic/{i}/',reason='INITIAL',body_bytes=1,status=200,
        started_UTC=f'2026-01-02T00:00:{i*6:02d}+00:00',completed_UTC=f'2026-01-02T00:00:{i*6+1:02d}+00:00')
    v.update(changes);return v


def test_normal_synthetic_request_response_never_issues_or_enables_permit():
    raw,md,q,design=fixture();report=d.inspect_synthetic_response(*seal(raw,md,q),design,now=NOW)
    assert not report['evidence_acquisition_authorized'] and not report['history_admission']
    assert report['B']==report['C']==report['D']=='HOLD' and not report['OS_TLS_proven']


@pytest.mark.parametrize('kind',['PERMIT_DESIGN_ONLY','real_http_collection109_v1',None])
def test_design_or_old_real_permit_not_an_executable_synthetic_grant(kind):
    _,_,q,design=fixture();design['kind']=kind
    with pytest.raises(d.DesignStop,match='NO_EXECUTABLE_PERMIT'):d.inspect_synthetic_request(q,design,now=NOW)


@pytest.mark.parametrize('field,value',[('approved_for_simulation',False),('expires_UTC',NOW),
    ('host_review',{}),('access_conditions_verified',False)])
def test_unapproved_expired_or_unknown_conditions_fail_closed(field,value):
    _,_,q,design=fixture();design[field]=value
    with pytest.raises(d.DesignStop):d.inspect_synthetic_request(q,design,now=NOW)


@pytest.mark.parametrize('url',['http://www.jleague.jp/synthetic/index/','https://www.jleague.jp.evil.invalid/synthetic/index/',
    'https://u:p@www.jleague.jp/synthetic/index/','https://www.jleague.jp:444/synthetic/index/',
    URL+'?x=1',URL+'#x',URL[:-1],URL.replace('/synthetic/','/%73ynthetic/'),
    'https://aboutj.jleague.jp/synthetic/index/','https://WWW.JLEAGUE.JP/synthetic/index/',
    'https://www.jleague.jp:443/synthetic/index/',' https://www.jleague.jp/synthetic/index/',
    'https://www.jleague.jp\\synthetic/index/','https://[bad/'])
def test_exact_URL_path_query_host_port_not_expanded_by_normalization(url):
    _,_,q,design=fixture();q['url']=url
    with pytest.raises(d.DesignStop):d.inspect_synthetic_request(q,design,now=NOW)


def test_hostname_comparison_is_normalized_without_authorizing_alternate_literal():
    assert d.url_parts('https://WWW.JLEAGUE.JP:443/synthetic/')['hostname']=='www.jleague.jp'
    assert d.url_parts(URL)['port']==443 and d.url_parts(URL)['query']==''


@pytest.mark.parametrize('field,value',[('method','HEAD'),('scope','REAL'),('source_revision','latest'),
    ('bucket','A'),('user_agent','browser impersonation'),('Cookie','session=1'),('Authorization','Bearer synthetic')])
def test_method_scope_revision_bucket_agent_and_credentials_refused(field,value):
    _,_,q,design=fixture();q[field]=value
    with pytest.raises(d.DesignStop):d.inspect_synthetic_request(q,design,now=NOW)


def test_duplicate_or_unfixed_target_not_implicitly_selected():
    _,_,q,design=fixture();design['rows']*=2
    with pytest.raises(d.DesignStop,match='DUPLICATED'):d.inspect_synthetic_request(q,design,now=NOW)
    design['rows']=design['rows'][:1];design['rows'][0]['fixed_for_simulation']=False
    with pytest.raises(d.DesignStop,match='UNCONFIRMED'):d.inspect_synthetic_request(q,design,now=NOW)


def test_two_budget_caps_not_interchangeable_and_global_six_bound():
    rows=[attempt(i,bucket='A') for i in range(4)]+[attempt(4),attempt(5)]
    assert d.inspect_budget(rows)['status']=='SYNTHETIC_ACCOUNTING_ONLY'
    rows[4]['bucket']='A'
    assert 'REQUEST_CAP_A' in d.inspect_budget(rows)['reasons']
    rows.append(attempt(6))
    assert 'GLOBAL_CAP' in d.inspect_budget(rows)['reasons']


@pytest.mark.parametrize('reason',['RETRY','REDIRECT','UNKNOWN'])
def test_retry_redirect_or_unknown_attempt_is_counted_then_rejected(reason):
    rows=[attempt(0),attempt(1,reason=reason)]
    report=d.inspect_budget(rows)
    assert report['total_attempts']==2 and report['counts']['B']==2
    assert report['status']=='STOP' and 'REDIRECT_RETRY_OR_UNKNOWN_ATTEMPT_FORBIDDEN' in report['reasons']


@pytest.mark.parametrize('status',[301,302,307,400,401,403,404,429,500,503])
def test_failure_responses_consume_budget_and_STOP(status):
    r=d.inspect_budget([attempt(status=status)])
    assert r['total_attempts']==1 and r['status']=='STOP'


def test_uncertain_end_is_consumed_and_cannot_continue():
    r=d.inspect_budget([attempt(completed_UTC=None,status=None),attempt(1)])
    assert r['total_attempts']==2 and 'UNKNOWN_COMPLETION_CONSUMED' in r['reasons']
    assert 'CONTINUED_AFTER_UNKNOWN_COMPLETION' in r['reasons']


def test_duplicate_URL_not_retried_and_failed_attempt_not_refunded():
    rows=[attempt(),attempt(1,url=attempt()['url'])]
    r=d.inspect_budget(rows);assert r['total_attempts']==2 and 'DUPLICATE_URL' in r['reasons']


def test_exact_five_seconds_after_completion_boundary():
    assert 'RATE_LIMIT' not in d.inspect_budget([attempt(),attempt(1)])['reasons']
    assert 'RATE_LIMIT' in d.inspect_budget([attempt(),attempt(1,started_UTC='2026-01-02T00:00:05.999999+00:00')])['reasons']


@pytest.mark.parametrize('bucket',['A','B'])
def test_body_total_cap_separate_from_request_count(bucket):
    r=d.inspect_budget([attempt(bucket=bucket,body_bytes=d.BYTE_CAPS[bucket]+1)])
    assert r['total_attempts']==1 and 'BODY_TOTAL_CAP_'+bucket in r['reasons']


@pytest.mark.parametrize('size',[-1,True,'100'])
def test_bad_body_counter_not_coerced(size):
    with pytest.raises(d.DesignStop):d.account_attempts([attempt(body_bytes=size)])


@pytest.mark.parametrize('path',['T:/synthetic-evidence/run-other/raw.bin','T:/synthetic-evidence/run/../outside/raw.bin',
    'Q:/synthetic-evidence/run/raw.bin','T:/synthetic-evidence/run/raw.bin:ADS','//host/share/raw.bin',
    'T:/synthetic-evidence/run/./raw.bin'])
def test_storage_boundary_not_string_prefix_or_traversal(path):
    with pytest.raises(d.DesignStop):d.inspect_storage_descriptor(storage(path=path))


@pytest.mark.parametrize('field,value',[('exclusive_create',False),('existing_file',True),('owner_verified',False),
    ('DACL_verified',False),('reparse_clear',False),('root_identity_before_publish','other-root'),('scope','REAL')])
def test_unknown_ownership_acl_reparse_or_root_replacement_rejected(field,value):
    with pytest.raises(d.DesignStop):d.inspect_storage_descriptor(storage(**{field:value}))


def test_storage_descriptor_does_not_claim_OS_ACL_validation():
    r=d.inspect_storage_descriptor(storage());assert not r['OS_ACL_proven'] and not r['execution_authorized']


@pytest.mark.parametrize('which',[0,1,2])
def test_raw_metadata_request_modification_rejected(which):
    raw,md,q,design=fixture();args=list(seal(raw,md,q));args[which]+=b' '
    with pytest.raises(d.DesignStop,match='SEALED_BYTES'):d.inspect_synthetic_response(*args,design,now=NOW)


@pytest.mark.parametrize('field,value',[('final_url','https://other.invalid/'),('request_id','other'),
    ('raw_SHA256','0'*64),('bytes',999),('complete_body',False),('automatic_retry',1),('redirects_followed',1),
    ('redirect_history',['unapproved']),('source_revision','other'),('bucket','A'),('source_identity','other'),
    ('storage_identity','other'),('access_control_detected',True),('authentication_required',True),
    ('first_publication_UTC','2020-01-01T00:00:00+00:00'),('request_started_UTC','2026-01-02'),
    ('response_completed_UTC','2026-01-02T00:00:11+00:00'),('snapshot_saved_UTC','2026-01-01T00:00:00+00:00'),
    ('audit_completed_UTC','2026-01-02T00:00:20+00:00')])
def test_internally_contradictory_metadata_even_resealed_refused(field,value):
    raw,md,q,design=fixture();md[field]=value
    with pytest.raises(d.DesignStop):d.inspect_synthetic_response(*seal(raw,md,q),design,now=NOW)


@pytest.mark.parametrize('tls_change',[dict(verified=False),dict(hostname_verified=False),dict(server_hostname='cdn.invalid')])
def test_bad_TLS_record_rejected_without_a_real_TLS_test(tls_change):
    raw,md,q,design=fixture();md['TLS'].update(tls_change)
    with pytest.raises(d.DesignStop):d.inspect_synthetic_response(*seal(raw,md,q),design,now=NOW)


def test_response_body_cap_checks_bytes_not_declared_length_only():
    raw,md,q,design=fixture();design['rows'][0]['body_cap']=len(raw)-1
    with pytest.raises(d.DesignStop,match='BODY_CAP'):d.inspect_synthetic_response(*seal(raw,md,q),design,now=NOW)


def test_robots_404_is_not_sitewide_permission_or_B_gate_clearance():
    raw,md,q,design=fixture('ROBOTS');md['status']=404
    r=d.inspect_synthetic_response(*seal(raw,md,q),design,now=NOW)
    assert r['robots_404_not_blanket_permission'] and not r['site_wide_permission_proven']
    assert r['B']==r['C']==r['D']=='HOLD'
    design['rows'][0]['kind']='TERMS'
    with pytest.raises(d.DesignStop,match='HTTP_STOP'):d.inspect_synthetic_response(*seal(raw,md,q),design,now=NOW)


def test_content_encoding_does_not_silently_expand_response():
    raw,md,q,design=fixture();md['headers']['Content-Encoding']='gzip'
    with pytest.raises(d.DesignStop):d.inspect_synthetic_response(*seal(raw,md,q),design,now=NOW)


@pytest.mark.parametrize('length,accepted',[(32763,True),(32764,False)])
def test_header_cap_boundary_is_independent_of_small_body(length,accepted):
    raw,md,q,design=fixture();md['headers']={'X':'a'*length}
    if accepted:
        assert not d.inspect_synthetic_response(*seal(raw,md,q),design,now=NOW)['evidence_acquisition_authorized']
    else:
        with pytest.raises(d.DesignStop,match='RESPONSE_HEADERS_CAP'):
            d.inspect_synthetic_response(*seal(raw,md,q),design,now=NOW)


def test_old_quarantine_references_never_admitted_or_reclassified():
    raw,md,q,design=fixture();md['related_fixture_ids']=['synthetic:old-quarantine-'+str(i) for i in range(9)]
    r=d.inspect_synthetic_response(*seal(raw,md,q),design,now=NOW)
    assert not r['history_admission'] and r['related_fixture_status']=='UNBOUND_REFERENCE_ONLY'
    assert r['B']==r['C']==r['D']=='HOLD'


def test_design_contract_has_no_HTTP_DNS_worker_model_filesystem_entrypoint():
    tree=ast.parse(FILE.read_text('utf8'))
    modules=[n.module for n in ast.walk(tree) if isinstance(n,ast.ImportFrom)]
    modules += [a.name for n in ast.walk(tree) if isinstance(n,ast.Import) for a in n.names]
    assert set(modules)<={'datetime','hashlib','json','pathlib','re','urllib.parse'}
    calls=[ast.unparse(n.func) for n in ast.walk(tree) if isinstance(n,ast.Call)]
    assert not any(n in {'open','exec','eval','Path'} or n.startswith(('socket','requests','subprocess','http'))
        or n.endswith(('.write_bytes','.write_text','.fit','.predict','.predict_proba')) for n in calls)
