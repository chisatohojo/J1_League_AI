"""Four immutable twelve-page boundaries; never resumes a failed or consumed run."""
from dataclasses import replace
from datetime import datetime, timezone
import json
from multibatch_http_worker import encoded, sha, require, now
from windows_local import read_bytes_locked, write_new_locked, acl_audit


def validate_batches(rows, batches):
    require(len(rows)==48 and len(batches)==4, 'EXACT_48_FOUR_BATCHES')
    require(len({r['url'] for r in rows})==len({r['identity'] for r in rows})==48,'DUPLICATE_BATCH_TARGET')
    require([b['batch'] for b in batches]==[1,2,3,4] and all(len(b['rows'])==12 for b in batches),'BATCH_SHAPE')
    require([r for b in batches for r in b['rows']]==rows,'BATCH_ORDER')


def audit_transport(manager, rows):
    """Independent reread of every completed GET at each batch boundary."""
    require(manager.sequence==len(rows)==len(manager.receipts) and manager.used=={r['url'] for r in rows},'GET_SET_OR_COUNT')
    ledger=[];previous_end=None;total=0
    acl_audit(manager.root)
    for i,(row,saved_parent) in enumerate(zip(rows,manager.receipts),1):
        folder=manager.root/('worker-%04d'%i);out=folder/'worker-output'
        parent_bytes=read_bytes_locked(folder/'parent-receipt.json');parent=json.loads(parent_bytes)
        req_bytes=read_bytes_locked(out/'request.json');req=json.loads(req_bytes)
        meta_bytes=read_bytes_locked(out/'metadata.json');meta=json.loads(meta_bytes)
        rec_bytes=read_bytes_locked(out/'worker-receipt.json');rec=json.loads(rec_bytes)
        raw=read_bytes_locked(out/'raw.html',2097152)
        require(parent==saved_parent and parent['status']=='HTTP_COMPLETE' and parent['final_owned_active_processes']==0,'UNCOMMITTED_OR_RESIDUAL_WORKER')
        require(parent['observed_exit']['exit_code']==0 and not parent['observed_exit']['timed_out'],'WORKER_EXIT')
        require(req['url']==meta['requested_url']==meta['final_url']==row['url'] and req['identity']==row['identity'],'GET_URL_IDENTITY')
        require(req['method']=='GET' and meta['status']==200 and meta['complete_body'] and meta['success'],'HTTP_COMPLETION')
        require(meta['sha256']==rec['raw_SHA256']==sha(raw) and meta['request_sha256']==rec['request_SHA256']==sha(req_bytes)
                and rec['metadata_SHA256']==sha(meta_bytes) and meta['bytes']==len(raw),'BOUNDARY_EVIDENCE_SHA')
        require(rec['PID']==req['PID']==parent['identity']['PID'] and parent['identity']['job_membership_verified'],'BOUNDARY_PROCESS_IDENTITY')
        require(req['task_SHA256']==rec['task_SHA256']==parent['task_SHA256']==sha(read_bytes_locked(folder/'task.json')),'BOUNDARY_TASK')
        require(req['permit_SHA256']==rec['permit_SHA256']==parent['permit_SHA256']==manager.permit_sha,'BOUNDARY_PERMIT')
        require(meta['GET_attempts']==rec['GET_attempts']==1 and meta['automatic_retries']==meta['redirects_followed']==0,'GET_RETRY_REDIRECT')
        require(meta['TLS']['verified'] and meta['TLS']['hostname_verified'] and meta['TLS']['server_hostname']==manager.permit['host'],'BOUNDARY_TLS')
        begin=datetime.fromisoformat(req['request_started_at_utc']);end=datetime.fromisoformat(meta['response_completed_at_utc'])
        require(begin.utcoffset()==end.utcoffset()==timezone.utc.utcoffset(None) and 0<=(end-begin).total_seconds()<=10,'BOUNDARY_UTC')
        require(previous_end is None or (begin-previous_end).total_seconds()>=5,'BATCH_BOUNDARY_RATE')
        previous_end=end;total+=len(raw)
        ledger.append({'ordinal':i,'url':row['url'],'identity':row['identity'],'raw_SHA256':sha(raw),'metadata_SHA256':sha(meta_bytes),
            'request_SHA256':sha(req_bytes),'worker_receipt_SHA256':sha(rec_bytes),'parent_receipt_SHA256':sha(parent_bytes)})
    require(total==manager.total and total<=manager.permit['total_body_cap'],'BOUNDARY_BODY_TOTAL')
    return ledger


def run_multibatch(offline, manager, store, items, strict, review, batches, access_check, *, blocked_urls=()):
    """Only this lazy iterator can advance the owned HTTP manager to another batch."""
    items=list(items);rows=[e.row for _,e in items];validate_batches(rows,batches)
    require(not {r['url'] for r in rows}&set(blocked_urls),'ALREADY_ACQUIRED')
    require(manager.permit['rows']==rows,'PERMIT_SELECTION_MISMATCH')
    runner=offline.ReplayRun(store,blocked_urls=blocked_urls);boundaries=[];accesses=[]

    def boundary(end):
        summary=runner.aggregate()
        require(summary['source_acquired']==summary['source_integrity_verified']==summary['receipt_count']==end,'UNCONFIRMED_BATCH_COUNT')
        require(summary['detail_PASS']+summary['detail_HOLD']==end and summary['quarantined']==summary['detail_HOLD']
                and summary['history_admitted']==0,'BATCH_HOLD_OR_ADMISSION')
        ledger=audit_transport(manager,rows[:end])
        # Reverify detached quarantine/review receipts; aggregate cannot omit HOLD packets.
        packets=[runner.verify_receipt(r['receipt'],r['SHA256']) for r in runner.records]
        require(all(p['source_integrity_verified'] and p['history_admission_status'] is False for p in packets),'BATCH_ADMISSION')
        number=end//12;name='batch-%02d'%number
        previous=boundaries[-1]['SHA256'] if boundaries else None
        doc={'batch':number,'committed_through':end,'PASS':sum(p['detail_analysis_status']=='PASS' for p in packets[-12:]),
             'HOLD':sum(p['detail_analysis_status']=='HOLD' for p in packets[-12:]),'source_sealed':12,'unconfirmed':0,
             'previous_boundary_SHA256':previous,'access_observation':accesses[-1],'UTC':now(),
             'receipt_SHA256':[r['SHA256'] for r in runner.records],'history_admission':False}
        seal=store.seal(name,{'packet.json':encoded(doc),'transport-ledger.json':encoded(ledger),'aggregate.json':encoded(summary)})
        receipt_name=name+'-receipt.json';receipt={'batch':number,'folder':name,'seal_SHA256':seal,'packet_SHA256':sha(encoded(doc)),'UTC':now()}
        pin=store.write(receipt_name,encoded(receipt))
        require(sha(store.read(receipt_name))==pin,'BATCH_RECEIPT_READBACK')
        require(sha(store.verify(name,seal)['packet.json'])==receipt['packet_SHA256'],'BATCH_SEAL_READBACK')
        boundaries.append({'receipt':receipt_name,'SHA256':pin,'batch':number})

    def delivered():
        for ordinal,(packet,expected) in enumerate(items,1):
            if (ordinal-1)%12==0:
                if boundaries:
                    prior=json.loads(store.read(boundaries[-1]['receipt']))
                    require(sha(store.read(boundaries[-1]['receipt']))==boundaries[-1]['SHA256'],'PREVIOUS_BOUNDARY_CHANGED')
                    store.verify(prior['folder'],prior['seal_SHA256'])
                observation=access_check((ordinal-1)//12+1)
                require(observation['allowed'] is True,'ACCESS_GATE_STOP')
                accesses.append(observation)
                store.write('batch-%02d-access.json'%((ordinal-1)//12+1),encoded(observation))
            raw,meta,req,folder=manager.one(expected.row)
            data=json.loads(meta)
            pins={'url':expected.row['url'],'raw_sha256':sha(raw),'metadata_sha256':sha(meta),'request_sha256':sha(req),
                  'response_completed_at_utc':data['response_completed_at_utc']}
            packet=replace(packet,raw=raw,metadata=meta,request=req,original_refs={'verified_worker_folder':str(folder)})
            yield packet,replace(expected,pins=pins)
            if ordinal%12==0:boundary(ordinal)

    def checked(*args):
        result=review(*args)
        require(not (result.get('status')=='HOLD' and str(result.get('reason','')).startswith(('TypeError:','KeyError:','IndexError:','UnicodeError:'))),'PARSER_CONTRACT_STOP')
        return result
    try:
        engine=runner.run(delivered(),strict,checked)
        require(engine['status']=='OFFLINE_REPLAY_COMPLETED' and len(boundaries)==4,'INCOMPLETE_MULTIBATCH_GLOBAL_STOP')
    except Exception as exc:
        engine={'status':'GLOBAL_STOP','reason':type(exc).__name__+':'+str(exc),'history_admitted':0,'committed_stage_B_receipts':len(runner.records)}
    manager.stopped=True
    states=[]
    for b in range(1,5):
        committed=next((v for v in boundaries if v['batch']==b),None)
        states.append({'batch':b,'status':'COMPLETED' if committed else 'STOPPED_UNCONFIRMED_BOUNDARY' if manager.sequence>(b-1)*12 else 'NOT_STARTED_AFTER_GLOBAL_STOP',
                       'receipt':committed,'started_URLs':min(12,max(0,manager.sequence-(b-1)*12))})
    result={'sealed_byte_engine':engine,'transport':'LIVE_HTTP','started_URLs':manager.sequence,'batch_states':states,
            'batch_receipts':boundaries,'access_checks':accesses,'history_admitted':0}
    write_new_locked(manager.root/'integration-terminal.json',encoded(result))
    return result,runner
