"""Synthetic independent249 execution, strict reviewed-rule scope and stops."""
import hashlib,importlib.util,json,os,socket,ssl,subprocess
from pathlib import Path
from types import SimpleNamespace
import pytest
from test_nn_reviewed_remark_contract import case,review

path=os.environ.get('J1AI_TIMING_EXECUTOR249')
rule_path=os.environ.get('J1AI_REMARK_REVIEW_RULE')
if not path or not rule_path:
    pytest.skip('Set J1AI_TIMING_EXECUTOR249 and J1AI_REMARK_REVIEW_RULE to sealed local artifacts',allow_module_level=True)
source=Path(path)
if hashlib.sha256(source.read_bytes()).hexdigest()!='6627cc2db07ddedf2e33985a1444b866ffaa7c99021061432b98916d0d5ddc9e':
    raise ValueError('Independent249 executor SHA mismatch')
spec=importlib.util.spec_from_file_location('executor249_local',source)
executor=importlib.util.module_from_spec(spec);spec.loader.exec_module(executor)
if hashlib.sha256(Path(rule_path).read_bytes()).hexdigest()!=executor.RULE_SHA:
    raise ValueError('Review-rule SHA mismatch')

@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def forbidden(*args,**kwargs):raise AssertionError('Synthetic tests cannot connect')
    monkeypatch.setattr(socket,'create_connection',forbidden)
    monkeypatch.setattr(socket.socket,'connect',forbidden)

def permit():
    rows=[{'identity':'fixture:'+str(i),'data_site_match_id':str(i),'series':'ongoing',
           'url':'https://data.j-league.or.jp/SFMS02/?match_card_id='+str(i),'complete_expected_header':'2026/27 synthetic full header'} for i in range(1000,1249)]
    return {'kind':'fixtures','approved':True,'network_enabled':True,'rows':rows,'max_total_GET':249,'batch_size':12,'max_batches':21,
            'allowed_host':executor.HOST,'timeout_seconds':10,'worker_deadline_seconds':10,'global_timeout_seconds':4500,
            'interval_seconds':5,'retries':0,'redirect_following':False,'parallel_downloads':0,'max_body_bytes':2097152,
            'max_total_body_bytes':522190848,'previous_39_URLs':['prior:'+str(i) for i in range(39)],
            'fixed_remaining_249_URLs':[r['url'] for r in rows],'selection_sha256':executor.sha(executor.encoded(rows)),
            'executor_sha256':executor.sha(source.read_bytes()),'parser_sha256':executor.CORE_SHA,
            'adapter_sha256':executor.ADAPTER_SHA,'review_rule_sha256':executor.RULE_SHA}

@pytest.mark.parametrize('change',['250','old276','old39','duplicate_ID','adapter','rule','parser','executor','changed_row',
                                  'host','retry','redirect','parallel','body','no_deadline'])
def test_independent_scope_and_SHA_cannot_expand(change):
    p=permit()
    if change=='250':p['rows'].append(dict(p['rows'][0]))
    if change=='old276':p['rows'].extend(dict(p['rows'][0]) for _ in range(27));p['max_total_GET']=276
    if change=='old39':p['previous_39_URLs'][0]=p['rows'][0]['url']
    if change=='duplicate_ID':p['rows'][1]['data_site_match_id']=p['rows'][0]['data_site_match_id']
    if change in ['adapter','rule','parser','executor']:p[{'adapter':'adapter_sha256','rule':'review_rule_sha256','parser':'parser_sha256','executor':'executor_sha256'}[change]]='0'*64
    if change=='changed_row':p['rows'][0]['complete_expected_header']='changed'
    if change=='host':p['allowed_host']='evil.test'
    if change=='retry':p['retries']=1
    if change=='redirect':p['redirect_following']=True
    if change=='parallel':p['parallel_downloads']=1
    if change=='body':p['max_total_body_bytes']+=1
    if change=='no_deadline':p['global_timeout_seconds']=None
    with pytest.raises(ValueError):executor.validate(p)

@pytest.mark.parametrize('status',[200,403,429,302])
def test_transport_is_one_TLS_verified_GET_without_retry_or_redirect(status,tmp_path,monkeypatch):
    calls=[]
    class Response:
        def __init__(self):self.status=status;self.body=b'synthetic'
        def getheaders(self):return [('Content-Type','text/html;charset=UTF-8')]
        def read(self,n):value,self.body=self.body[:n],self.body[n:];return value
    class Connection:
        def __init__(self,host,port,timeout,context):
            assert host==executor.HOST and port==443 and timeout==10
            assert context.check_hostname and context.verify_mode==ssl.CERT_REQUIRED
        def request(self,method,path,headers):calls.append((method,path))
        def getresponse(self):return Response()
        def close(self):pass
    monkeypatch.setattr(executor,'safe',lambda path:Path(path))
    meta=executor.worker(permit(),'a'*64,1,tmp_path,Connection)
    assert calls==[('GET','/SFMS02/?match_card_id=1000')] and meta['success']==(status==200)
    assert meta['GET_attempts']==1 and meta['automatic_retries']==meta['redirects_followed']==0
    assert executor.sha((tmp_path/'raw.html').read_bytes())==meta['sha256']
    with pytest.raises(ValueError):executor.worker(permit(),'a'*64,1,tmp_path,Connection)

@pytest.mark.parametrize('outcome',['all_PASS','unknown_role','timing','HTTP_429','timeout','batch2_fail','last_page_fail'])
def test21_batches_last9_and_terminal_global_stop(outcome,tmp_path,monkeypatch):
    p=permit();plans=[{'batch':i+1,'rows':p['rows'][i*12:(i+1)*12]} for i in range(21)]
    planpath=tmp_path/'plan.json';planpath.write_bytes(executor.encoded(plans));access=tmp_path/'access';access.write_bytes(b'{}')
    p.update(input_SHA256={},core_path='core',guard_path='guard',adapter_path='adapter',review_rule_path=rule_path,
             access_raw_path=str(access),access_metadata_path=str(access),team_master_path='unused',batch_plan_path=str(planpath))
    path=tmp_path/'permit.json';raw=executor.encoded(p);path.write_bytes(raw)
    monkeypatch.setattr(executor,'safe',lambda path:Path(path))
    monkeypatch.setattr(executor,'load_module',lambda path,*args:SimpleNamespace(access_gate=lambda *args:{'network_enabled':True}))
    import src.collect.teams
    monkeypatch.setattr(src.collect.teams,'load_team_master',lambda path:object())
    def analyze(*args):
        hold=outcome in ['unknown_role','timing']
        return {'status':'HOLD' if hold else 'PASS','hold_reason':'UNKNOWN_NOTE' if hold else None,
                'stop_stage':'strict_parser' if outcome=='timing' else 'reviewed_remark_adapter' if hold else None,
                'remarks_classification':'UNKNOWN_FORMAT' if hold else 'EMPTY','strict_analysis':{},'adapter_analysis':{}}
    monkeypatch.setattr(executor,'analyze_saved',analyze)
    clock=[0.0];calls=[];starts=[]
    monkeypatch.setattr(executor.time,'monotonic',lambda:clock[0])
    monkeypatch.setattr(executor.time,'sleep',lambda seconds:clock.__setitem__(0,clock[0]+seconds))
    def run(command,timeout,capture_output):
        assert timeout==10 and capture_output
        ordinal=int(command[-1]);calls.append(ordinal);starts.append(clock[0]);clock[0]+=.25
        if outcome=='timeout':raise subprocess.TimeoutExpired(command,timeout)
        folder=tmp_path/f'batch-{(ordinal-1)//12+1:02d}'/f'request_{(ordinal-1)%12+1:02d}';assert not any(folder.iterdir())
        ok=outcome!='HTTP_429' and not (outcome=='batch2_fail' and ordinal==13) and not (outcome=='last_page_fail' and ordinal==249)
        request=b'{}';body=b'synthetic';meta={'success':ok,'status':200 if ok else 429,'bytes':len(body),'sha256':executor.sha(body),
            'request_sha256':executor.sha(request),'request_started_at_utc':'2026-10-20T10:00:00+00:00','response_completed_at_utc':'2026-10-20T10:00:01+00:00'}
        (folder/'request.json').write_bytes(request);(folder/'raw.html').write_bytes(body);(folder/'metadata.json').write_bytes(executor.encoded(meta))
        (folder/'snapshot-save-receipt.json').write_bytes(executor.encoded({'snapshot_saved_at_utc':'2026-10-20T10:00:01+00:00'}))
        return SimpleNamespace(returncode=0,stderr=b'')
    monkeypatch.setattr(executor.subprocess,'run',run)
    report=executor.execute(path,executor.sha(raw))
    count=249 if outcome in ['all_PASS','last_page_fail'] else 13 if outcome=='batch2_fail' else 1
    assert calls==list(range(1,count+1)) and report['attempted']==count and report['not_attempted']==249-count
    assert len(report['batch_records'])==21 and all(b-a>=5.25 for a,b in zip(starts,starts[1:]))
    assert report['status']==('DETAIL_EVIDENCE_ACQUIRED_RESEARCH_ONLY' if outcome=='all_PASS' else 'HOLD_BOUNDED_EVIDENCE_ACQUISITION')
    assert report['HISTORY']==report['PREDICTION']=='HOLD'
    if outcome=='all_PASS':assert report['batch_records'][-1]['selected']==report['batch_records'][-1]['PASS']==9
    before=len(calls)
    with pytest.raises(FileExistsError):executor.execute(path,executor.sha(raw))
    assert len(calls)==before

def test_other_fixture_interpreter_warning_cannot_use_reviewed_rule(tmp_path):
    c=case()
    for name,body in [('raw.html',c['raw']),('metadata.json',c['meta']),('request.json',c['request'])]:(tmp_path/name).write_bytes(body)
    row={**c['row'],'complete_expected_header':c['header']};core=SimpleNamespace(analyze=lambda *args:c['base'])
    result=executor.analyze_saved(tmp_path,row,{},object(),core,review,json.loads(Path(rule_path).read_bytes()))
    assert result['status']=='HOLD' and result['stop_stage']=='reviewed_remark_adapter'
    assert result['hold_reason']=='UNKNOWN_NON_TIMING_REMARK_REQUIRES_REVIEW'

def test_integrity_failure_never_reaches_the_parser(tmp_path):
    c=case()
    for name,body in [('raw.html',c['raw']+b' '),('metadata.json',c['meta']),('request.json',c['request'])]:(tmp_path/name).write_bytes(body)
    core=SimpleNamespace(analyze=lambda *args:pytest.fail('Parser must not see altered packet'))
    result=executor.analyze_saved(tmp_path,{**c['row'],'complete_expected_header':c['header']},{},object(),core,review,{})
    assert result['status']=='HOLD' and result['stop_stage']=='packet_integrity'

def test_existing_source_output_path_is_rejected(tmp_path):
    with pytest.raises(ValueError,match='outside_new_research_root'):executor.write(tmp_path,'raw.html',b'forbidden')
