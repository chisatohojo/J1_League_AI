"""Forty-eight-page research multibatch. Owned jobs and sealed Stage A/B; no history admission."""
from contextlib import ExitStack
from dataclasses import replace
import json
import os
from pathlib import Path
import time
from windows_local import DirectoryLease, OwnedJob, Close, open_handle, acl_audit, secure_mkdir, read_bytes_locked, write_new_locked
from local_integration import leased_store_class, LocalManager
from multibatch_http_worker import validate, encoded, sha, now, require, AGENT


class HttpManager:
    def __init__(self,new_root,*,allowed_base,permit_path,permit_sha,worker_path,blocked_urls=(),previous_completion=None):
        self.root=Path(os.path.abspath(new_root));base=Path(allowed_base).resolve()
        require(self.root.is_relative_to(base) and self.root!=base,'APPROVED_NEW_ROOT')
        self.base_lease=DirectoryLease(self.root.parent);self.held=[];self.receipts=[];self.used=set();self.sequence=0;self.total=0;self.stopped=False
        self.permit_path=Path(permit_path).resolve();self.permit_sha=permit_sha;self.worker=Path(worker_path).resolve()
        self.blocked=frozenset(blocked_urls);self.last_end=previous_completion;self.started=time.monotonic()
        try:
            self.acl=secure_mkdir(self.root);self.lease=DirectoryLease(self.root)
            permit_bytes=read_bytes_locked(self.permit_path);require(sha(permit_bytes)==permit_sha,'PERMIT_SHA');self.permit=json.loads(permit_bytes)
            validate(self.permit,{'kind':'APPROVED_SINGLE_GET','row':self.permit['rows'][0],'ordinal':1})
            require(str(self.root)==self.permit['output_root'],'OUTPUT_BINDING')
            require(not self.blocked&{r['url'] for r in self.permit['rows']},'PREVIOUSLY_ACQUIRED')
            require(self.permit['code_files'].get(str(self.worker))==sha(read_bytes_locked(self.worker)),'WORKER_PIN')
            for name,pin in self.permit['code_files'].items():
                self.held.append(open_handle(name,0x80000000,1,3));require(sha(read_bytes_locked(name))==pin,'CODE_SHA')
            self.held.append(open_handle(self.permit_path,0x80000000,1,3))
            # Shared approval claim prevents another output root from reusing this permit.
            write_new_locked(self.permit_path.with_suffix('.consumed.json'),encoded({'permit_SHA256':permit_sha,'UTC':now(),'PID':os.getpid(),'output_root':str(self.root)}))
            write_new_locked(self.root/'run-claim.json',encoded({'permit_SHA256':permit_sha,'UTC':now(),'single_use':True}))
        except BaseException:
            self.close();raise

    def one(self,row):
        require(not self.stopped,'TERMINAL_NO_RESTART')
        try:return self._one(row)
        except BaseException:self.stopped=True;raise

    def _one(self,row):
        require(time.monotonic()-self.started<self.permit['global_deadline_seconds'],'GLOBAL_DEADLINE')
        require(self.sequence<len(self.permit['rows']) and row==self.permit['rows'][self.sequence],'FIXED_ORDER')
        require(row['url'] not in self.used and row['url'] not in self.blocked,'ALREADY_CONSUMED_NO_RETRY')
        if self.last_end is not None:
            delay=5-(time.monotonic()-self.last_end)
            if delay>0:time.sleep(delay)
        require(time.monotonic()-self.started<self.permit['global_deadline_seconds'],'GLOBAL_DEADLINE')
        acl_audit(self.root)
        self.used.add(row['url']);self.sequence+=1
        folder=self.root/('worker-%04d'%self.sequence);secure_mkdir(folder)
        with DirectoryLease(folder),ExitStack() as stack:
            output=folder/'worker-output';secure_mkdir(output);stack.enter_context(DirectoryLease(output))
            task={'kind':'APPROVED_SINGLE_GET','ordinal':self.sequence,'row':row,'permit_path':str(self.permit_path),'permit_SHA256':self.permit_sha}
            task_path=folder/'task.json';task_sha=write_new_locked(task_path,encoded(task))['SHA256']
            # Persist intent before the suspended worker is launched. An uncertain exit consumes this URL.
            write_new_locked(folder/'consumed-intent.json',encoded({'UTC':now(),'row':row,'task_SHA256':task_sha,'retry':False}))
            identity=observed=cleanup=None;stop=None;result=None
            launched=time.time_ns()
            with OwnedJob() as job:
                try:
                    identity=job.start(['-B',self.worker,'--task',task_path,task_sha],folder)
                    observed=job.wait(self.permit['parent_deadline_seconds'])
                    settle=time.monotonic()+.2
                    while job.active() and not observed['timed_out'] and time.monotonic()<settle:time.sleep(.005)
                    if observed['timed_out'] or observed['exit_code']!=0 or job.active():raise RuntimeError('WORKER_TIMEOUT_EXIT_OR_RESIDUE')
                    for p in (self.root,folder,output):acl_audit(p)
                    raw=read_bytes_locked(output/'raw.html',self.permit['body_cap']);meta=read_bytes_locked(output/'metadata.json');req=read_bytes_locked(output/'request.json')
                    receipt=json.loads(read_bytes_locked(output/'worker-receipt.json'));metadata=json.loads(meta);request=json.loads(req)
                    require(receipt['PID']==request['PID']==identity['PID'] and receipt['task_SHA256']==request['task_SHA256']==task_sha,'WORKER_BINDING')
                    require(receipt['permit_SHA256']==request['permit_SHA256']==self.permit_sha,'PERMIT_BINDING')
                    require(receipt['raw_SHA256']==metadata['sha256']==sha(raw) and receipt['metadata_SHA256']==sha(meta)
                            and receipt['request_SHA256']==metadata['request_sha256']==sha(req),'BODY_METADATA_RECEIPT_SHA')
                    require(metadata['requested_url']==metadata['final_url']==request['url']==row['url'],'RESPONSE_URL')
                    require(metadata['TLS']['verified'] and metadata['TLS']['hostname_verified'] and metadata['TLS']['server_hostname']==self.permit['host'],'TLS_BINDING')
                    require(metadata['status'] in ({200} if self.permit['kind']=='DETAIL' else {200,404}),'HTTP_STATUS_STOP')
                    require(receipt['GET_attempts']==metadata['GET_attempts']==1 and metadata['redirects_followed']==metadata['automatic_retries']==0,'GET_POLICY')
                    require(0<len(raw)<=self.permit['body_cap'] and self.total+len(raw)<=self.permit['total_body_cap'],'BODY_TOTAL')
                    self.total+=len(raw);result=(raw,meta,req,folder)
                except Exception as exc:
                    stop=type(exc).__name__+':'+str(exc)
                    if job.process:cleanup=job.cleanup(2)
                active=job.active()
                if active:stop='OWNED_PROCESS_REMAINS';cleanup=job.cleanup(2)
                active=job.active()
            # More conservative than response completion: rate is measured from worker/cleanup completion.
            self.last_end=time.monotonic()
            receipt={'ordinal':self.sequence,'status':'STOP' if stop else 'HTTP_COMPLETE','reason':stop,'identity':identity,
                'observed_exit':observed,'cleanup':cleanup,'final_owned_active_processes':active,'task_SHA256':task_sha,
                'permit_SHA256':self.permit_sha,'launched_epoch_ns':launched,'parent_completed_UTC':now(),
                'started_URLs':self.sequence,'GET_upper_bound':self.sequence,'no_retry':True}
            write_new_locked(folder/'parent-receipt.json',encoded(receipt));self.receipts.append(receipt)
            if stop:raise RuntimeError('GLOBAL_STOP:'+stop)
            return result

    def close(self):
        self.stopped=True
        for h in getattr(self,'held',[]):Close(h)
        self.held=[]
        if hasattr(self,'lease'):self.lease.close()
        if hasattr(self,'base_lease'):self.base_lease.close()


def run_stage(offline,manager,store,items,strict,review,*,live=False,blocked_urls=()):
    """Lazy delivery ensures verified quarantine/receipt precedes the next owned worker."""
    runner=offline.ReplayRun(store,blocked_urls=blocked_urls)
    def delivered():
        for packet,expected in items:
            if live:
                raw,meta,req,folder=manager.one(expected.row)
                data=json.loads(meta)
                pins={'url':expected.row['url'],'raw_sha256':sha(raw),'metadata_sha256':sha(meta),'request_sha256':sha(req),
                      'response_completed_at_utc':data['response_completed_at_utc']}
                expected=replace(expected,pins=pins)
                packet=replace(packet,raw=raw,metadata=meta,request=req,original_refs={'verified_worker_folder':str(folder)})
            else:packet=manager.one(packet)
            yield packet,expected
    def checked(*args):
        result=review(*args)
        require(not (result.get('status')=='HOLD' and str(result.get('reason','')).startswith(('TypeError:','KeyError:','IndexError:','UnicodeError:'))),'PARSER_CONTRACT_STOP')
        return result
    try: result=runner.run(delivered(),strict,checked)
    except Exception as exc:
        result={'status':'GLOBAL_STOP','reason':type(exc).__name__+':'+str(exc),'history_admitted':0,'committed_stage_B_receipts':len(runner.records)}
    manager.stopped=True
    # Old engine is a sealed-byte validator. Its network counters are not transport accounting.
    result={'sealed_byte_engine':result,'transport':'LIVE_HTTP' if live else 'OFFLINE_LOCAL_WORKER',
            'started_URLs':manager.sequence,'actual_transport_receipts':manager.receipts,'history_admitted':0}
    write_new_locked(manager.root/'integration-terminal.json',encoded(result))
    return result,runner


def access_policy(raw,meta,urls,at_utc,*,known_404_sha):
    """A conservative local gate, not a statement of blanket site permission."""
    from datetime import datetime
    from urllib.robotparser import RobotFileParser
    require(meta['requested_url']==meta['final_url']=='https://data.j-league.or.jp/robots.txt','ROBOTS_EXACT_URL')
    require(sha(raw)==meta['sha256'] and len(raw)==meta['bytes'] and len(raw)<=65536,'ROBOTS_SHA_SIZE')
    age=(datetime.fromisoformat(at_utc)-datetime.fromisoformat(meta['response_completed_at_utc'])).total_seconds()
    require(0<=age<=86400,'STALE_ACCESS_WITNESS')
    if meta['status']==404:
        require(sha(raw)==known_404_sha,'UNKNOWN_404_BODY_REQUIRES_REVIEW')
        return {'status':'EXACT_ROBOTS_URL_HAS_NO_PUBLISHED_RULES','site_wide_permission_proven':False,'age_seconds':age,'minimum_interval':5}
    require(meta['status']==200 and meta['content_type'].lower().startswith('text/plain'),'UNKNOWN_ACCESS_RESPONSE')
    text=raw.decode('utf-8-sig'); directives=[]
    for line in text.splitlines():
        line=line.split('#',1)[0].strip()
        if not line:continue
        require(':' in line,'UNKNOWN_ROBOTS_STRUCTURE')
        key,value=line.split(':',1); key=key.lower().strip()
        require(key in {'user-agent','allow','disallow','crawl-delay','request-rate','sitemap'},'UNKNOWN_ROBOTS_DIRECTIVE')
        directives.append(key)
    require('user-agent' in directives,'UNKNOWN_EMPTY_ROBOTS')
    parser=RobotFileParser();parser.parse(text.splitlines())
    require(all(parser.can_fetch(AGENT,u) for u in urls),'ROBOTS_DISALLOW')
    require((parser.crawl_delay(AGENT) or 0)<=5,'ROBOTS_STRICTER_DELAY_HOLD')
    rate=parser.request_rate(AGENT)
    require(rate is None or rate.seconds/rate.requests<=5,'ROBOTS_STRICTER_RATE_HOLD')
    return {'status':'PUBLISHED_ROBOTS_RULES_CHECKED','age_seconds':age,'minimum_interval':5,'site_wide_permission_proven':False}
