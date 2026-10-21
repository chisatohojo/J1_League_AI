"""Synthetic postprocessing faults only; no network or models."""
from copy import deepcopy
import socket
import pytest
import importlib.util
from pathlib import Path
spec=importlib.util.spec_from_file_location('postprocess_contract',Path(__file__).parents[1]/'research/nn_v2/phase2_5B_16/postprocess_contract.py')
c=importlib.util.module_from_spec(spec);spec.loader.exec_module(c)

@pytest.fixture(autouse=True)
def offline(monkeypatch):
 def deny(*args,**kwargs):raise AssertionError('No network during postprocessing')
 monkeypatch.setattr(socket.socket,'connect',deny);monkeypatch.setattr(socket,'getaddrinfo',deny)

def fixture():
 ledger=[{'ordinal':i,'url':'synthetic:'+str(i),'identity':'fixture:'+str(i),'SHA256':str(i)} for i in range(1,49)]
 boundaries=[deepcopy(ledger[:i*12]) for i in range(1,5)]
 return ledger,boundaries,{'source_acquired':48,'detail_PASS':45,'detail_HOLD':3,'history_admitted':0}

def test_original_prefixes_and_three_HOLD_preserved():
 ledger,boundaries,counts=fixture();assert c.verify_prefixes(ledger,boundaries,counts,3,3)['HOLD']==3

@pytest.mark.parametrize('fault',['prefix','reorder','duplicate','dropped_hold','unacquired_hold','admission','extra_get','extra_continuation'])
def test_faults_refused(fault):
 ledger,boundaries,counts=fixture();continued=3
 if fault=='prefix':boundaries[1][0]['SHA256']='modified'
 if fault=='reorder':boundaries[0].reverse()
 if fault=='duplicate':ledger[1]=deepcopy(ledger[0])
 if fault=='dropped_hold':counts.update(detail_PASS=48,detail_HOLD=0)
 if fault=='unacquired_hold':counts['source_acquired']=45
 if fault=='admission':counts['history_admitted']=1
 if fault=='extra_get':ledger.append(deepcopy(ledger[0]))
 if fault=='extra_continuation':continued=4
 with pytest.raises(ValueError):c.verify_prefixes(ledger,boundaries,counts,3,continued)
