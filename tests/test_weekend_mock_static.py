"""Static regressions and inert configuration checks, without worker imports."""
import ast
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET

from test_weekend_mock_contract import no_connections_or_child_processes
from src.modeling import weekend_mock_contract as c

ROOT = Path(__file__).resolve().parents[1]


def test_pure_contract_has_only_allowed_stdlib_imports_and_no_entrypoint():
    tree = ast.parse((ROOT/'src/modeling/weekend_mock_contract.py').read_text(encoding='utf8'))
    allowed = {'dataclasses', 'datetime', 'hashlib', 'json', 'math', 're'}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            assert all(n.name in allowed for n in node.names)
        elif isinstance(node, ast.ImportFrom):
            assert node.module in allowed
    assert not any(isinstance(n, ast.FunctionDef) and n.name == 'main' for n in tree.body)
    assert not any(isinstance(n, ast.If) and '__name__' in ast.unparse(n.test) for n in tree.body)


def test_no_io_process_network_clock_or_estimator_calls_in_pure_contract():
    tree = ast.parse((ROOT/'src/modeling/weekend_mock_contract.py').read_text(encoding='utf8'))
    banned = {'open', 'Path', 'eval', 'exec', 'compile', '__import__', 'subprocess.Popen', 'os.system', 'os.replace'}
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            call = ast.unparse(node.func)
            assert call not in banned
            assert not call.startswith(('socket.', 'subprocess.', 'urllib.', 'requests.', 'joblib.', 'pickle.'))
            assert not call.endswith(('.fit', '.predict', '.predict_proba', '.now', '.utcnow'))


def test_Phase4_code_and_contract_pins_remain_identical():
    evidence = json.loads((ROOT/'docs/WEEKEND_BATCH_PHASE4_VALIDATION.json').read_bytes())
    for name, digest in evidence['code_and_contract_SHA256'].items():
        assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest() == digest


def test_Phase5A_code_and_design_pins_remain_identical():
    evidence = json.loads((ROOT/'docs/WEEKEND_BATCH_PHASE5A_VALIDATION.json').read_bytes())
    assert hashlib.sha256((ROOT/'docs/WEEKEND_BATCH_PHASE5A.md').read_bytes()).hexdigest() == evidence['documentation_SHA256']
    for name, digest in evidence['code_SHA256'].items():
        assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest() == digest


def test_sandbox_template_has_no_host_mapping_or_command_and_disables_network():
    root = ET.fromstring(c.sandbox_template())
    assert root.tag == 'Configuration'
    assert {n.tag for n in root} == {'Networking', 'ClipboardRedirection', 'VGpu'}
    assert len(list(root)) == 3 and all(n.text == 'Disable' and not n.attrib and not list(n) for n in root)
    assert root.find('MappedFolders') is None and root.find('LogonCommand') is None


def test_existing_target_column_names_match_but_synthetic_namespace_is_not_a_real_binding():
    tree = ast.parse((ROOT/'src/modeling/champion_prediction.py').read_text(encoding='utf8'))
    columns = ast.literal_eval(next(n.value for n in tree.body if isinstance(n, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == 'TARGET_COLUMNS' for t in n.targets)))
    assert set(columns) == c.TARGET_KEYS and len(columns) == 7
    # This check is data-schema compatibility, not an adapter or an admission.
    assert c.SCOPE == 'SYNTHETIC_ONLY' and c.MOCK != 'operational_champion_20260922_v1'
