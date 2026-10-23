"""Pure offline B/C/D audit decisions, never result-event admission rules.

The outer auditor verifies source/revision/packet seals and supplies reviewed
facts. Missing times remain unknown. No file, network, worker or model APIs.
"""
from datetime import datetime, timedelta, timezone
import hashlib
import json
import re
from urllib.parse import urlsplit, parse_qs


class EvidenceStop(RuntimeError):
    """Integrity/identity contradiction, distinct from an evidence-gap HOLD."""


def trust(condition, reason):
    if not condition:
        raise EvidenceStop(reason)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def stamp(value):
    try:
        result = datetime.fromisoformat(value)
    except (ValueError, TypeError) as exc:
        raise EvidenceStop('INVALID_CLOCK') from exc
    trust(result.utcoffset() is not None, 'NAIVE_CLOCK')
    return result


def verify_acquisition(raw, metadata_raw, request_raw, expected):
    """Verify the three sealed bytes and preserve actual acquisition times.

    Supports only the recorded metadata fields, not guessed publication dates.
    HTTP Date and filesystem mtime are deliberately not used as event times.
    """
    row, pins = expected['row'], expected['pins']
    for value, key in [(raw,'raw_sha256'),(metadata_raw,'metadata_sha256'),(request_raw,'request_sha256')]:
        trust(type(value) is bytes and sha(value)==pins[key], 'PACKET_SHA:'+key)
    md, request = json.loads(metadata_raw), json.loads(request_raw)
    url = row['url']; parsed = urlsplit(url)
    exact = re.fullmatch(r'https://data\.j-league\.or\.jp/SFMS02/\?match_card_id=([1-9][0-9]*)',url)
    trust(parsed.scheme=='https' and parsed.netloc=='data.j-league.or.jp' and parsed.path=='/SFMS02/'
          and not parsed.fragment and exact is not None and exact[1]==row['data_site_match_id']
          and parse_qs(parsed.query)=={'match_card_id':[row['data_site_match_id']]}, 'URL_NAMESPACE_ID')
    trust(md['requested_url']==md['final_url']==request['url']==pins['url']==url, 'URL_BINDING')
    trust(md['sha256']==sha(raw) and md['request_sha256']==sha(request_raw)
          and type(md['bytes']) is int and md['bytes']==len(raw), 'RAW_REQUEST_RELATION')
    trust(type(md['status']) is int and md['status']==200 and md['success'] is True
          and md['complete_body'] is True and request['method']=='GET', 'COMPLETE_SUCCESSFUL_SOURCE_REQUIRED')
    trust(request['identity']==row['identity'] and md.get('identity',row['identity'])==row['identity'], 'IDENTITY_BINDING')
    started, finished = md['request_started_at_utc'], md['response_completed_at_utc']
    trust(started==request['request_started_at_utc'] and finished==pins['response_completed_at_utc'], 'ACQUISITION_CLOCK_BINDING')
    trust(stamp(started).utcoffset()==timedelta(0) and stamp(finished).utcoffset()==timedelta(0)
          and stamp(started)<=stamp(finished), 'UTC_ORDER')
    if 'snapshot_saved_at_utc' in md:
        trust(stamp(finished)<=stamp(md['snapshot_saved_at_utc']), 'SNAPSHOT_BEFORE_RESPONSE')
    if 'fetched_at_utc' in md:
        trust(md['fetched_at_utc']==finished, 'FETCHED_CLOCK_CONTRADICTION')
    return dict(request_started_UTC=started,response_completed_UTC=finished,
        snapshot_saved_UTC=md.get('snapshot_saved_at_utc'),raw_sha256=sha(raw),
        metadata_sha256=sha(metadata_raw),request_sha256=sha(request_raw),
        result_observed_available_by_UTC=finished,first_result_publication_UTC=None,
        historical_publication_asof_proven=False)


SEMANTIC_ROW_KEYS = ('identity','home_team_id','away_team_id','source_date',
                     'source_reported_kickoff','home_score_90','away_score_90','pk_played','extra_time_played')


def unchanged_semantics(current, prior, row):
    trust(current==prior and current['identity']==row['identity']
          and current['status']=='PARSE_VERIFIED_FINAL_RECORD_ONLY', 'STRICT_ANALYSIS_CONTRADICTION')
    trust(current['official_date']==row['source_date'] and current['official_kickoff']==row['source_reported_kickoff'][11:16], 'FACT_DATE_KICKOFF_CONTRADICTION')
    parsed = current['parsed']
    for side in ['home','away']:
        trust(type(row[side+'_score_90']) is int and row[side+'_score_90']>=0
              and parsed[side+'_score_90']==row[side+'_score_90'], 'REGULATION_RESULT_CONTRADICTION')
    trust(parsed['extra_time_played']==row['extra_time_played']
          and (parsed['home_pk_score'] is not None)==row['pk_played'], 'PK_ET_CONTRADICTION')
    return True


def axis(values):
    trust(all(v in {'ESTABLISHED','NOT_ESTABLISHED','UNKNOWN'} for v in values.values()), 'INVALID_EVIDENCE_STATE')
    return dict(status='PASS' if all(v=='ESTABLISHED' for v in values.values()) else 'HOLD',components=values)


def classify(facts):
    """Classify verified audit facts; never invent a cutoff, time or trace.

    A target's own final score is not a feature dependency. D examines a real
    registered cutoff and its complete PRIOR-result trace, if one exists.
    """
    trust(facts['A_verified'] is True, 'A_INTEGRITY_NOT_VERIFIED')
    B = axis(dict(recorded_kickoff='ESTABLISHED',final_regulation_record='ESTABLISHED',
        result_acquisition_upper_bound='ESTABLISHED',actual_start_chronology=facts['actual_start'],
        interruption_resumption_chain=facts['interruption_chain'],
        end_and_result_availability_chronology=facts['completion_chronology']))
    C = axis(dict(original_announcement=facts['original_announcement'],
        change_notice_chain=facts['change_notice_chain'],
        notice_acquisition=facts['notice_acquisition']))
    cutoff, trace = facts['prediction_cutoff'], facts['history_trace']
    if cutoff is None or trace is None:
        D = axis(dict(actual_prediction_cutoff='UNKNOWN' if cutoff is None else 'ESTABLISHED',
            complete_prior_result_trace='UNKNOWN',asof_source_acquisition='UNKNOWN'))
    else:
        prediction = stamp(cutoff); feature = stamp(facts['feature_cutoff']); kickoff = stamp(facts['kickoff'])
        trust(feature<=prediction<kickoff, 'CUTOFF_KICKOFF_ORDER')
        seen=set(); valid=True
        for item in trace:
            trust(item['identity']!=facts['identity'] and item['identity'] not in seen, 'TARGET_OR_DUPLICATE_IN_HISTORY_TRACE')
            seen.add(item['identity'])
            trust(item['verified_packet'] is True and item['source_revision'], 'UNVERIFIED_HISTORY_SOURCE')
            for key in ['raw_sha256','metadata_sha256','request_sha256']:
                trust(re.fullmatch(r'[0-9a-f]{64}',item[key]) is not None, 'HISTORY_SOURCE_SHA')
            # The frozen adapter admits a previous day's result at the next
            # midnight boundary (<=), separately from its actual knowledge UTC.
            valid = valid and stamp(item['actual_acquisition_UTC'])<=prediction and stamp(item['result_effective_policy_at'])<=feature
        D = axis(dict(actual_prediction_cutoff='ESTABLISHED',
            complete_prior_result_trace='ESTABLISHED' if facts['history_complete_verified'] else 'NOT_ESTABLISHED',
            asof_source_acquisition='ESTABLISHED' if valid else 'NOT_ESTABLISHED'))
    return dict(A='PASS',B=B,C=C,D=D,history_admission=False,prediction_authorized=False)


def require_history_admission(_report):
    raise EvidenceStop('HISTORY_ADMISSION_NOT_AUTHORIZED')


def schedule_draft(rows, now, count=20):
    """Saved-schedule feasibility only; never select/register a real R_start/T0."""
    today=stamp(now).astimezone(timezone(timedelta(hours=9))).date(); groups={}
    for row in rows:
        groups.setdefault(int(row['round']),[]).append(row)
    future=[]
    for number, group in sorted(groups.items()):
        if len(group)==10 and all(r['status']=='scheduled' and datetime.fromisoformat(r['match_date']).date()>today for r in group):
            future.append((number,group))
    example=future[:count]; flat=[r for _,g in example for r in g]
    return dict(saved_complete_unstarted_rounds=len(future),saved_scheduled_fixtures=sum(len(g) for _,g in future),
        illustrative_rounds=[n for n,_ in example],illustrative_fixture_count=len(flat),
        missing_kickoffs=sum(not r['kickoff_time'] for r in flat),
        missing_match_page_ID=sum(not r['match_page_id'] for r in flat),
        missing_data_site_ID=sum(not r['data_site_match_id'] for r in flat),
        proposed_20_rounds_exist_in_saved_observation=len(example)==count,
        T0=None,R_start=None,enrolled_fixtures=0,status='HOLD_NO_T0_OR_FRESH_REGISTRATION')
