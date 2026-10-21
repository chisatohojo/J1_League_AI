"""Offline post-acquisition prefix/count audit; no worker, HTTP or admission path."""
def verify_prefixes(final_ledger,boundaries,source_counts,quarantine_count,continued):
 """Pure audit checks; no network, model, worker or mutable source access."""
 if len(final_ledger)!=48 or len(boundaries)!=4:raise ValueError('EXACT_48_FOUR_REQUIRED')
 if len({v['url'] for v in final_ledger})!=48 or len({v['identity'] for v in final_ledger})!=48:raise ValueError('DUPLICATE')
 for i,ledger in enumerate(boundaries,1):
  if ledger!=final_ledger[:i*12]:raise ValueError('BOUNDARY_PREFIX_MISMATCH')
 if source_counts['source_acquired']!=48 or source_counts['detail_PASS']+source_counts['detail_HOLD']!=48:raise ValueError('COUNT_MISMATCH')
 if source_counts['detail_HOLD']!=quarantine_count or not 0<=continued<=quarantine_count:raise ValueError('QUARANTINE_MISMATCH')
 if source_counts['history_admitted']!=0:raise ValueError('ADMISSION_FORBIDDEN')
 return {'sources':48,'PASS':source_counts['detail_PASS'],'HOLD':quarantine_count,'quarantine_continuations':continued}
