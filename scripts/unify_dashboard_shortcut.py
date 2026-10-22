"""Explicit Windows desktop migration: plan first, reviewed apply, exact rollback.

Import/help never accesses Desktop. No server, feed generator or task is started.
Plans/backups contain private paths: keep them outside Git.
"""
import argparse
import ctypes
from ctypes import wintypes
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
MARKER = 'J1AI unified dashboard shortcut v1 | '
FIELDS = ('TargetPath', 'Arguments', 'WorkingDirectory', 'IconLocation', 'Description')
COM_SCRIPT = r'''
[Console]::InputEncoding = [Text.UTF8Encoding]::new($false)
[Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
$ErrorActionPreference='Stop'
$q = [Console]::In.ReadToEnd() | ConvertFrom-Json
$shell=New-Object -ComObject WScript.Shell
$s=$null
try {
 $s=$shell.CreateShortcut($q.path)
 if ($q.action -eq 'write') {
  foreach ($n in @('TargetPath','Arguments','WorkingDirectory','IconLocation','Description')) { $s.$n=$q.fields.$n }
  $s.WindowStyle=1
  $s.Save()
 }
 $value=[ordered]@{}
 foreach ($n in @('TargetPath','Arguments','WorkingDirectory','IconLocation','Description')) { $value[$n]=$s.$n }
 $value | ConvertTo-Json -Compress
} finally {
 if ($s) { [void][Runtime.InteropServices.Marshal]::ReleaseComObject($s) }
 [void][Runtime.InteropServices.Marshal]::ReleaseComObject($shell)
}
'''


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def safe(path):
    """Reject traversal/reparse ancestors before filesystem operations; no ACL repair."""
    p = Path(path).absolute()
    if '..' in Path(path).parts:
        raise ValueError('Path traversal refused')
    for item in [p, *p.parents]:
        if item.exists() and item.lstat().st_file_attributes & 1024:
            raise ValueError('Reparse path refused')
    return p


def save(path, data):
    safe(path)
    with Path(path).open('xb') as f:
        f.write(data); f.flush(); os.fsync(f.fileno())
    if Path(path).read_bytes() != data:
        raise ValueError('Write/readback failed')


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + '\n').encode('utf8')


def link(path, fields=None):
    if sys.platform != 'win32':
        raise ValueError('Windows required')
    safe(path)
    if fields is None and not Path(path).is_file():
        raise ValueError('Missing shortcut')
    if fields is not None and Path(path).exists():
        raise ValueError('Shortcut collision')
    query = {'action': 'write' if fields is not None else 'read', 'path': str(path), 'fields': fields}
    p = subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', COM_SCRIPT],
                       input=json.dumps(query, ensure_ascii=False).encode('utf8'), stdout=subprocess.PIPE,
                       stderr=subprocess.PIPE, timeout=20, creationflags=0x08000000, check=True)
    return json.loads(p.stdout.decode('utf-8-sig'))


def argv(command):
    shell = ctypes.WinDLL('shell32', use_last_error=True)
    shell.CommandLineToArgvW.argtypes = (wintypes.LPCWSTR, ctypes.POINTER(ctypes.c_int))
    shell.CommandLineToArgvW.restype = ctypes.POINTER(wintypes.LPWSTR)
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.LocalFree.argtypes = (ctypes.c_void_p,)
    count = ctypes.c_int()
    ptr = shell.CommandLineToArgvW('pythonw.exe ' + command, ctypes.byref(count))
    if not ptr:
        raise ValueError('Invalid command line')
    try:
        return [ptr[i] for i in range(1, count.value)]
    finally:
        kernel.LocalFree(ptr)


def desktop_paths():
    query = "[Environment]::GetFolderPath('DesktopDirectory')"
    active = subprocess.check_output(['powershell.exe', '-NoProfile', '-Command', query], timeout=10).decode().strip()
    result = [Path(active), Path.home() / 'Desktop']
    for n in ['OneDrive', 'OneDriveConsumer', 'OneDriveCommercial']:
        if os.environ.get(n): result.append(Path(os.environ[n]) / 'Desktop')
    return list(dict.fromkeys(p.absolute() for p in result if p.is_dir()))


def same(a, b):
    return os.path.normcase(str(Path(a).absolute())) == os.path.normcase(str(Path(b).absolute()))


def legacy_owned(fields, registered):
    root = Path(fields['WorkingDirectory'])
    if not any(same(root, p) for p in registered): return False
    args = argv(fields['Arguments'])
    if args[:1] == ['-B']: args = args[1:]
    if not args or not same(args[0], root / 'scripts/launch_dashboard.py'): return False
    if len(args[1:]) % 2: return False
    pairs = list(zip(args[1::2], args[2::2])); opts = dict(pairs)
    if len(pairs) != len(opts) or set(opts) - {'--runtime','--view','--store-sha','--python','--browser-mode'}: return False
    if not {'--runtime','--view','--python'} <= set(opts): return False
    if opts['--view'] not in {'rounds','retrospective'}: return False
    if opts['--view'] == 'retrospective' and (len(opts.get('--store-sha','')) != 64): return False
    if opts.get('--browser-mode','app') not in {'app','default'}: return False
    if not same(fields['TargetPath'], Path(opts['--python']).with_name('pythonw.exe')): return False
    marker = ('J1AI Champion A retrospective default-browser launcher v1 | ' + str(root)
              if opts.get('--browser-mode') == 'default' else
              ('J1AI Champion A retrospective launcher v1 | ' if opts['--view']=='retrospective' else 'J1AI Champion A launcher v1 | ') + str(root) + ' | ' + opts['--runtime'])
    return fields['Description'] == marker and all(safe(p).is_file() for p in [args[0], opts['--python'], fields['TargetPath']])


def plan(python, data, *, folders=None, registered=None):
    from scripts.serve_dashboard import load_dashboard_data
    python, data = safe(python), safe(data)
    load_dashboard_data(data)  # strict existing Champion schema; no generation
    if python.name.lower() != 'python.exe' or not python.is_file(): raise ValueError('Explicit python.exe required')
    folders = desktop_paths() if folders is None else folders
    if registered is None:
        text = subprocess.check_output(['git','worktree','list','--porcelain'], cwd=ROOT, timeout=10).decode('utf8')
        registered = [line[9:] for line in text.splitlines() if line.startswith('worktree ')]
    old, ignored = [], []
    for folder in folders:
        safe(folder)
        for p in sorted(folder.iterdir()):
            if p.suffix.lower() not in {'.lnk','.url'} or not any(n in p.name.lower() for n in ['j1','champion','predict']): continue
            safe(p)
            fields = link(p) if p.suffix.lower()=='.lnk' else {}
            if fields and legacy_owned(fields, registered):
                old.append({'path':str(p),'SHA256':sha(p),'fields':fields,'launcher_SHA256':sha(Path(fields['WorkingDirectory'])/'scripts/launch_dashboard.py')})
            else:
                ignored.append({'path':str(p),'reason':'Unrecognized ownership; untouched'})
    if not old: raise ValueError('No verified owned legacy shortcuts; STOP')
    dest = safe(Path(folders[0])/'J1AI.lnk')
    if dest.exists(): raise ValueError('J1AI shortcut already exists; STOP without overwrite')
    launcher = ROOT/'scripts/launch_dashboard.py'; icon = ROOT/'web/assets/j1ai.ico'
    pythonw = python.with_name('pythonw.exe')
    pins = {str(p):sha(p) for p in [python,pythonw,data,launcher,icon,Path(__file__)]}
    fields = dict(TargetPath=str(pythonw), WorkingDirectory=str(ROOT), IconLocation=str(icon)+',0',
                  Description=MARKER+str(ROOT), Arguments=subprocess.list2cmdline(['-B',str(launcher),'--data',str(data),'--python',str(python),'--browser-mode','default']))
    return {'version':1,'root':str(ROOT),'desktop':str(folders[0]),'destination':str(dest),'new_fields':fields,'old':old,'ignored':ignored,
            'pins':pins,'mode':'DRY_RUN_ONLY','data_scope':'Existing schema-v1 Champion display snapshot; no retrospective store conversion or feed generation'}


def validate_plan(p):
    if p['version'] != 1 or not same(p['root'],ROOT) or p['mode'] != 'DRY_RUN_ONLY': raise ValueError('Wrong plan owner/version')
    if not same(Path(p['destination']).parent,p['desktop']) or Path(p['destination']).name != 'J1AI.lnk': raise ValueError('Destination mismatch')
    for name,h in p['pins'].items():
        if sha(safe(name)) != h: raise ValueError('Plan input changed; create/review a fresh plan')
    # Rebuild the entire desired contract, including executable/data arguments.
    args=argv(p['new_fields']['Arguments']); opts=dict(zip(args[2::2],args[3::2]))
    fresh=plan(Path(opts['--python']),Path(opts['--data']),folders=[Path(p['desktop'])],registered=[r['fields']['WorkingDirectory'] for r in p['old']])
    if fresh != p: raise ValueError('Desktop/ownership/arguments changed since dry run; STOP')


def apply(p, backup):
    validate_plan(p)
    backup=safe(backup)
    if backup.exists(): raise ValueError('Backup directory must be new')
    backup.mkdir()
    for i,r in enumerate(p['old']): save(backup/('%03d.lnk'%i),Path(r['path']).read_bytes())
    proposed=backup/'proposed-J1AI.lnk'; link(proposed,p['new_fields'])
    if link(proposed)!=p['new_fields']: raise ValueError('COM link roundtrip mismatch')
    manifest={'plan':p,'new_SHA256':sha(proposed),'backup_SHA256':{r.name:sha(r) for r in backup.glob('*.lnk')}}
    save(backup/'manifest.json',encoded(manifest))
    # Verify every original again after the durable backup, before any Desktop mutation.
    for r in p['old']:
        if sha(safe(r['path'])) != r['SHA256'] or link(r['path']) != r['fields']: raise ValueError('Original changed during backup')
    save(p['destination'],proposed.read_bytes())
    if link(p['destination']) != p['new_fields']: raise ValueError('New shortcut verification failed; retain backup and STOP')
    for r in p['old']:
        if sha(safe(r['path'])) != r['SHA256']: raise ValueError('Original changed before removal')
        Path(r['path']).unlink()
    save(backup/'applied.json',encoded({'status':'APPLIED','manifest_SHA256':sha(backup/'manifest.json')}))


def rollback(backup):
    backup=safe(backup); m=json.loads((backup/'manifest.json').read_bytes()); p=m['plan']
    if not same(p['root'],ROOT): raise ValueError('Backup owner mismatch')
    if (Path(p['destination']).name!='J1AI.lnk' or not same(Path(p['destination']).parent,p['desktop'])
            or p['new_fields']['Description']!=MARKER+str(ROOT)):
        raise ValueError('Backup destination/ownership mismatch')
    if (backup/'applied.json').exists() and json.loads((backup/'applied.json').read_bytes())['manifest_SHA256']!=sha(backup/'manifest.json'):
        raise ValueError('Backup manifest changed')
    for n,h in m['backup_SHA256'].items():
        if Path(n).name != n or sha(safe(backup/n)) != h: raise ValueError('Backup SHA mismatch')
    dest=safe(p['destination'])
    if dest.exists() and (sha(dest)!=m['new_SHA256'] or link(dest)!=p['new_fields']): raise ValueError('New shortcut changed; rollback STOP')
    for i,r in enumerate(p['old']):
        path=safe(r['path'])
        if path.suffix.lower()!='.lnk' or not same(path.parent,p['desktop']): raise ValueError('Rollback outside approved Desktop')
        if not legacy_owned(r['fields'],[r['fields']['WorkingDirectory']]): raise ValueError('Original owner mismatch')
        if path.exists() and sha(path)!=r['SHA256']: raise ValueError('Original filename collision; rollback STOP')
        if sha(backup/('%03d.lnk'%i)) != r['SHA256']: raise ValueError('Original backup mismatch')
    for i,r in enumerate(p['old']):
        if not Path(r['path']).exists(): save(r['path'],(backup/('%03d.lnk'%i)).read_bytes())
        if link(r['path'])!=r['fields']: raise ValueError('Restored target mismatch')
    if dest.exists(): dest.unlink()  # exact new SHA checked above; never another link
    save(backup/'rolled-back.json',encoded({'status':'ROLLED_BACK','manifest_SHA256':sha(backup/'manifest.json')}))


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest='command',required=True)
    dry=sub.add_parser('plan'); dry.add_argument('--python',type=Path,required=True);dry.add_argument('--data',type=Path,required=True);dry.add_argument('--output',type=Path,required=True)
    change=sub.add_parser('apply');change.add_argument('--plan',type=Path,required=True);change.add_argument('--confirm-desktop-migration',action='store_true',required=True)
    undo=sub.add_parser('rollback');undo.add_argument('--backup',type=Path,required=True)
    args=parser.parse_args(argv)
    if sys.platform!='win32':parser.error('Windows required')
    if args.command=='plan':
        p=plan(args.python,args.data);save(args.output,encoded(p));print('DRY RUN ONLY:',len(p['old']),'verified links -> J1AI.lnk. Review the private plan; Desktop unchanged.')
    elif args.command=='apply':
        p=json.loads(args.plan.read_bytes());backup=Path(os.environ['LOCALAPPDATA'])/'J1AI'/'ShortcutBackups'
        safe(backup);backup.mkdir(parents=True,exist_ok=True);dest=backup/uuid.uuid4().hex
        apply(p,dest);print('Applied. Private rollback backup:',dest)
    else:rollback(args.backup);print('Rollback verified.')
    return 0


if __name__=='__main__':
    raise SystemExit(main())
