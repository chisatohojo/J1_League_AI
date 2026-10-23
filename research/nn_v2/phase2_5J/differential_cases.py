"""Synthetic offline comparison recipes, never saved official evidence."""
import hashlib

from research.nn_v2.phase2_5H import robots_offline as old
from research.nn_v2.phase2_5I import robots_normative as prior
from research.nn_v2.phase2_5J import robots_layers as current


def cases():
    # category, source anchors and independent expected decisions are explicit.
    # The layer changes do not imply old evidence or HTTP decisions were wrong.
    data=[
        ('agent_case',b'User-agent: examplebot\nDisallow: /','/x',('DENY','DENY','DENY'),'OLD_AND_NEW_AGREE','section-2.2.1'),
        ('agent_substring',b'User-agent: Bot\nDisallow: /\nUser-agent: *\nAllow: /','/x',('DENY','ALLOW','ALLOW'),'CORRECTED_NEW','section-2.2.1'),
        ('group_merge',b'User-agent: ExampleBot\nDisallow: /a\nUser-agent: ExampleBot\nAllow: /a','/a',('ALLOW','ALLOW','ALLOW'),'OLD_AND_NEW_AGREE','section-2.2.1'),
        ('named_not_wildcard',b'User-agent: *\nDisallow: /\nUser-agent: ExampleBot\nAllow: /','/a',('ALLOW','ALLOW','ALLOW'),'OLD_AND_NEW_AGREE','section-2.2.1'),
        ('wildcard',b'User-agent: *\nDisallow: /a*b','/axb',('DENY','DENY','DENY'),'OLD_AND_NEW_AGREE','section-2.2.3'),
        ('anchor',b'User-agent: *\nDisallow: /x$','/xx',('ALLOW','ALLOW','ALLOW'),'OLD_AND_NEW_AGREE','section-2.2.3'),
        ('longest',b'User-agent: *\nDisallow: /x\nAllow: /x/public','/x/public',('ALLOW','ALLOW','ALLOW'),'OLD_AND_NEW_AGREE','section-2.2.2'),
        ('google_marker_rank',b'User-agent: *\nAllow: /page\nDisallow: /*.htm','/page.htm',('ALLOW','UNKNOWN','UNKNOWN'),'SPEC_UNCLEAR_HOLD','section-2.2.2'),
        ('allow_tie',b'User-agent: *\nAllow: /x\nDisallow: /x','/x',('ALLOW','ALLOW','ALLOW'),'OLD_AND_NEW_AGREE','section-2.2.2'),
        ('literal_star',b'User-agent: *\nDisallow: /file-%2A.html','/file-*.html',('ALLOW','DENY','DENY'),'CORRECTED_NEW','section-2.2.3'),
        ('literal_dollar',b'User-agent: *\nDisallow: /file-%24','/file-$',('ALLOW','DENY','DENY'),'CORRECTED_NEW','section-2.2.3'),
        ('unreserved',b'User-agent: *\nDisallow: /~user','/%7Euser',('DENY','DENY','DENY'),'OLD_AND_NEW_AGREE','section-2.2.2'),
        ('UTF8',b'User-agent: *\nDisallow: /%E3%83%84','/%E3%83%84',('DENY','DENY','DENY'),'OLD_AND_NEW_AGREE','section-2.2.2'),
        ('encoded_slash',b'User-agent: *\nDisallow: /foo/bar','/foo%2Fbar',('ALLOW','UNKNOWN','UNKNOWN'),'SPEC_UNCLEAR_HOLD','section-2.2.2'),
        ('query_ascii_pair',b'User-agent: *\nDisallow: /search?q=foo','/search?q=foo',('DENY','UNKNOWN','DENY'),'CORRECTED_NEW','section-2.2.2'),
        ('query_reserved_data',b'User-agent: *\nDisallow: /search?q=https://foo.bar','/search?q=https://foo.bar',('DENY','UNKNOWN','UNKNOWN'),'SPEC_UNCLEAR_HOLD','section-2.2.2'),
        ('unknown_record',b'User-agent: *\nX-review: retain\nDisallow: /private','/private',('UNKNOWN','UNKNOWN','DENY'),'CORRECTED_NEW','section-2.2.4'),
        ('unknown_record_allow',b'User-agent: *\nCrawl-delay: 9\nDisallow: /private','/public',('UNKNOWN','UNKNOWN','ALLOW'),'CORRECTED_NEW','section-2.2.4'),
        ('empty',b'','/public',('UNKNOWN','UNKNOWN','ALLOW'),'CORRECTED_NEW','section-2.2.1'),
        ('comment_only',b'# saved comment\n\n','/public',('UNKNOWN','UNKNOWN','ALLOW'),'CORRECTED_NEW','section-2.2.1'),
        ('invalid_defined_rule',b'User-agent: *\nDisallow: *.gif$','/a.gif',('UNKNOWN','UNKNOWN','UNKNOWN'),'SPEC_UNCLEAR_HOLD','section-2.2'),
        ('invalid_UTF8',b'\xff','/a',('UNKNOWN','UNKNOWN','UNKNOWN'),'INTENTIONAL_J1AI_REFUSAL','section-2.3.1.5'),
        ('malformed',b'User-agent: *\nDisallow /private','/private',('UNKNOWN','UNKNOWN','UNKNOWN'),'INTENTIONAL_J1AI_REFUSAL','section-2.3.1.5'),
        ('malformed_percent',b'User-agent: *\nDisallow: /private','/%ZZ',('UNKNOWN','UNKNOWN','UNKNOWN'),'INTENTIONAL_J1AI_REFUSAL','section-2.2.2'),
    ]
    prefix=b'User-agent: *\nDisallow: /private\n#'
    for size in [65535,65536,65537,512000]:
        raw=prefix+b'x'*(size-len(prefix))
        value='ALLOW' if size<=65536 else 'UNKNOWN'
        data.append(('size_'+str(size),raw,'/public',(value,value,value),
            'OLD_AND_NEW_AGREE' if size<=65536 else 'INTENTIONAL_J1AI_REFUSAL','section-2.5'))
    return [dict(id=key,raw=raw,path=path,expected=list(expected),category=category,RFC_anchor=anchor,
        Google_anchor='order-of-precedence-for-rules' if key=='google_marker_rank' else 'syntax' if 'record' in key else 'file-format' if key.startswith('size_') else 'url-matching-based-on-path-values')
        for key,raw,path,expected,category,anchor in data]


def compare(case):
    raw=case['raw'];digest=hashlib.sha256(raw).hexdigest()
    shared=dict(source_host='synthetic.invalid',target_url='https://synthetic.invalid'+case['path'],
        user_agent='ExampleBot/1.0',expected_raw_SHA256=digest)
    h=old.evaluate(raw,**shared,parser_version=old.VERSION,profile=old.SYNTHETIC_PROFILE)
    i=prior.evaluate(raw,**shared,parser_version=prior.VERSION,profile=prior.SYNTHETIC_PROFILE,
        product_token='ExampleBot',specification_SHA256=prior.SPEC_SHAS)
    j=current.evaluate(raw,**shared,profile=prior.SYNTHETIC_PROFILE,product_token='ExampleBot',specification_SHA256=prior.SPEC_SHAS)
    actual=[h['decision'],i['decision'],j['layer1']['decision']]
    if actual!=case['expected']:raise AssertionError((case['id'],actual,case['expected']))
    return dict(id=case['id'],category=case['category'],input=dict(raw_SHA256=digest,bytes=len(raw),
        raw_UTF8=raw.decode('utf8') if len(raw)<1024 and case['id']!='invalid_UTF8' else None,
        fixture_recipe='differential_cases.cases:'+case['id'],URL=shared['target_url'],User_Agent=shared['user_agent'],product_token='ExampleBot'),
        RFC_anchor=case['RFC_anchor'],Google_anchor=case['Google_anchor'],expected_decisions=case['expected'],
        H_synthetic=h,I_synthetic=i,J_layers=j,old_official_evidence_rewritten=False)
