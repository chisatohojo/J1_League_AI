"""Test-only Windows children. No model, transport, runtime or task entrypoint.

The parent creates suspended processes, verifies kernel identity, assigns an
exclusive Job, then resumes. Children can write only the NEW marked test arena.
Python audit hooks are defense in depth, not an OS network/filesystem sandbox.
"""
import ctypes
from ctypes import wintypes as T
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import uuid


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def require(value, reason):
    if not value:
        raise RuntimeError(reason)


class STARTUPINFO(ctypes.Structure):
    _fields_ = [("cb", T.DWORD), ("lpReserved", T.LPWSTR), ("lpDesktop", T.LPWSTR),
                ("lpTitle", T.LPWSTR), ("dwX", T.DWORD), ("dwY", T.DWORD),
                ("dwXSize", T.DWORD), ("dwYSize", T.DWORD), ("dwXCountChars", T.DWORD),
                ("dwYCountChars", T.DWORD), ("dwFillAttribute", T.DWORD),
                ("dwFlags", T.DWORD), ("wShowWindow", T.WORD), ("cbReserved2", T.WORD),
                ("lpReserved2", ctypes.POINTER(T.BYTE)), ("hStdInput", T.HANDLE),
                ("hStdOutput", T.HANDLE), ("hStdError", T.HANDLE)]


class PROCESSINFO(ctypes.Structure):
    _fields_ = [("hProcess", T.HANDLE), ("hThread", T.HANDLE),
                ("dwProcessId", T.DWORD), ("dwThreadId", T.DWORD)]


class BASICLIMIT(ctypes.Structure):
    _fields_ = [("PerProcessUserTimeLimit", ctypes.c_longlong), ("PerJobUserTimeLimit", ctypes.c_longlong),
                ("LimitFlags", T.DWORD), ("MinimumWorkingSetSize", ctypes.c_size_t),
                ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", T.DWORD),
                ("Affinity", ctypes.c_size_t), ("PriorityClass", T.DWORD), ("SchedulingClass", T.DWORD)]


class EXTENDEDLIMIT(ctypes.Structure):
    _fields_ = [("BasicLimitInformation", BASICLIMIT), ("IoInfo", ctypes.c_ulonglong * 6),
                ("ProcessMemoryLimit", ctypes.c_size_t), ("JobMemoryLimit", ctypes.c_size_t),
                ("PeakProcessMemoryUsed", ctypes.c_size_t), ("PeakJobMemoryUsed", ctypes.c_size_t)]


class API:
    def __init__(self):
        require(os.name == 'nt', 'Windows test only')
        self.k = ctypes.WinDLL('kernel32', use_last_error=True)
        signatures = {
            'CreateJobObjectW': ([T.LPVOID, T.LPCWSTR], T.HANDLE),
            'OpenJobObjectW': ([T.DWORD, T.BOOL, T.LPCWSTR], T.HANDLE),
            'SetInformationJobObject': ([T.HANDLE, ctypes.c_int, T.LPVOID, T.DWORD], T.BOOL),
            'QueryInformationJobObject': ([T.HANDLE, ctypes.c_int, T.LPVOID, T.DWORD, T.LPVOID], T.BOOL),
            'AssignProcessToJobObject': ([T.HANDLE, T.HANDLE], T.BOOL),
            'IsProcessInJob': ([T.HANDLE, T.HANDLE, ctypes.POINTER(T.BOOL)], T.BOOL),
            'TerminateJobObject': ([T.HANDLE, T.UINT], T.BOOL),
            'TerminateProcess': ([T.HANDLE, T.UINT], T.BOOL),
            'CreateProcessW': ([T.LPCWSTR, T.LPWSTR, T.LPVOID, T.LPVOID, T.BOOL, T.DWORD,
                                T.LPVOID, T.LPCWSTR, ctypes.POINTER(STARTUPINFO), ctypes.POINTER(PROCESSINFO)], T.BOOL),
            'ResumeThread': ([T.HANDLE], T.DWORD),
            'GetProcessTimes': ([T.HANDLE, ctypes.POINTER(T.FILETIME), ctypes.POINTER(T.FILETIME),
                                 ctypes.POINTER(T.FILETIME), ctypes.POINTER(T.FILETIME)], T.BOOL),
            'QueryFullProcessImageNameW': ([T.HANDLE, T.DWORD, T.LPWSTR, ctypes.POINTER(T.DWORD)], T.BOOL),
            'GetExitCodeProcess': ([T.HANDLE, ctypes.POINTER(T.DWORD)], T.BOOL),
            'WaitForSingleObject': ([T.HANDLE, T.DWORD], T.DWORD),
            'CloseHandle': ([T.HANDLE], T.BOOL),
            'GetCurrentProcess': ([], T.HANDLE),
            'OpenProcess': ([T.DWORD,T.BOOL,T.DWORD],T.HANDLE),
        }
        for name, (args, result) in signatures.items():
            fn = getattr(self.k, name); fn.argtypes = args; fn.restype = result
        self.n = ctypes.WinDLL('ntdll')
        self.n.NtQueryInformationProcess.argtypes = [T.HANDLE, T.ULONG, T.LPVOID, T.ULONG, ctypes.POINTER(T.ULONG)]
        self.n.NtQueryInformationProcess.restype = T.LONG

    @staticmethod
    def ok(value):
        if not value:
            raise ctypes.WinError(ctypes.get_last_error())

    def in_job(self, process, job):
        result = T.BOOL()
        self.ok(self.k.IsProcessInJob(process, job, ctypes.byref(result)))
        return bool(result.value)

    def process_identity(self, process):
        values = [T.FILETIME() for _ in range(4)]
        self.ok(self.k.GetProcessTimes(process, *[ctypes.byref(v) for v in values]))
        image, size = ctypes.create_unicode_buffer(32768), T.DWORD(32768)
        self.ok(self.k.QueryFullProcessImageNameW(process, 0, image, ctypes.byref(size)))
        return dict(creation_filetime=(values[0].dwHighDateTime << 32) | values[0].dwLowDateTime,
                    executable=str(Path(image.value).resolve()))

    def creation_time(self, process):
        # QueryFullProcessImageName can fail for an already exited process.
        # The retained kernel handle plus GetProcessTimes still pins identity.
        values = [T.FILETIME() for _ in range(4)]
        self.ok(self.k.GetProcessTimes(process, *[ctypes.byref(v) for v in values]))
        return (values[0].dwHighDateTime << 32) | values[0].dwLowDateTime

    def command_line(self, process):
        class UNICODE(ctypes.Structure):
            _fields_ = [('Length', T.USHORT), ('MaximumLength', T.USHORT), ('Buffer', T.LPVOID)]
        length = T.ULONG()
        self.n.NtQueryInformationProcess(process, 60, None, 0, ctypes.byref(length))
        require(0 < length.value <= 131072, 'kernel command line size')
        buffer = ctypes.create_string_buffer(length.value)
        status = self.n.NtQueryInformationProcess(process, 60, buffer, len(buffer), ctypes.byref(length))
        require(status == 0, 'kernel command line unavailable')
        value = ctypes.cast(buffer, ctypes.POINTER(UNICODE)).contents
        return ctypes.wstring_at(value.Buffer, value.Length // 2)


class OwnedJob:
    """Never accepts PID-only termination or an existing Job/worker entrypoint."""
    def __init__(self, arena):
        arena.check()
        self.arena, self.api, self.children = arena, API(), []
        if not (arena.root/'control').exists():
            arena.mkdir('control')
        self.name = 'Local\\J1AI.StagingTest.' + uuid.uuid4().hex
        self.handle = self.api.k.CreateJobObjectW(None, self.name)
        self.api.ok(self.handle)
        require(ctypes.get_last_error() != 183, 'Job must be create-new')
        limits = EXTENDEDLIMIT()
        limits.BasicLimitInformation.LimitFlags = 0x2000 | 0x8  # KILL_ON_JOB_CLOSE, active limit.
        limits.BasicLimitInformation.ActiveProcessLimit = 4
        self.api.ok(self.api.k.SetInformationJobObject(self.handle, 9, ctypes.byref(limits), ctypes.sizeof(limits)))
        self.closed = False

    def spawn(self, operation, *, request_id='a'*64, pauses=(), source=None, refuse_assignment=False):
        self.arena.check()
        require(operation in {'claim', 'publish', 'mutate', 'observe'}, 'test entrypoint allowlist')
        require(not self.closed, 'Job closed')
        if not (self.arena.root/'control').exists():
            self.arena.mkdir('control')
        marker = self.arena.root/'process-scope.json'
        if not marker.exists():
            self.arena.write_new('process-scope.json', json.dumps(dict(scope='TEST_STORAGE_CHILD_ONLY',
                nonce=uuid.uuid4().hex, production_enabled=False), sort_keys=True).encode())
        scope = json.loads(marker.read_bytes())
        require(set(scope)=={'scope','nonce','production_enabled'} and scope['scope']=='TEST_STORAGE_CHILD_ONLY'
                and scope['production_enabled'] is False, 'test owner scope')
        nonce = uuid.uuid4().hex
        helper = Path(__file__).resolve()
        storage = helper.parents[1]/'src/modeling/weekend_staging_windows.py'
        executable = Path(sys._base_executable).resolve()
        request = dict(operation=operation, request_id=request_id, nonce=nonce, job=self.name,
            root=str(self.arena.root), root_id=list(self.arena.root_id), acl=self.arena.acl,
            scope_sha256=sha(marker), helper_sha256=sha(helper), storage_sha256=sha(storage),
            pauses=list(pauses), source=source)
        relative = 'control/'+nonce+'.request.json'
        self.arena.write_new(relative, json.dumps(request, sort_keys=True).encode())
        command = subprocess.list2cmdline([str(executable), '-I', '-B', '-W', 'error', str(helper),
                                          '--test-child', str(self.arena.root/relative)])
        startup, info = STARTUPINFO(), PROCESSINFO()
        startup.cb = ctypes.sizeof(startup)
        startup.dwFlags = 1; startup.wShowWindow = 0
        self.api.ok(self.api.k.CreateProcessW(str(executable), ctypes.create_unicode_buffer(command), None, None,
                    False, 0x4 | 0x8, None, str(self.arena.root), ctypes.byref(startup), ctypes.byref(info)))
        # DETACHED_PROCESS avoids a hidden conhost.exe Job member. Merely using
        # CREATE_NO_WINDOW was observed to allocate one; that evidence is kept.
        child = dict(process=info.hProcess, pid=info.dwProcessId, nonce=nonce, command_line=command,
                     executable_sha256=sha(executable), request=request, resumed=False)
        self.children.append(child)
        try:
            child['identity'] = self.api.process_identity(info.hProcess)
            require(Path(child['identity']['executable']) == executable, 'wrong process image')
            require(self.api.command_line(info.hProcess) == command, 'kernel command line mismatch')
            child['kernel_command_line_verified'] = True
            assigned = False if refuse_assignment else self.api.k.AssignProcessToJobObject(self.handle, info.hProcess)
            if not assigned:
                # The just-created suspended handle is ours; it has never run.
                self.api.ok(self.api.k.TerminateProcess(info.hProcess, 0xE1))
                require(self.api.k.WaitForSingleObject(info.hProcess, 5000) == 0, 'suspended cleanup timeout')
                child['assignment_refused_before_resume'] = True
                return child
            require(self.api.in_job(info.hProcess, self.handle), 'explicit Job membership missing')
            child['job_verified_before_resume'] = True
            require(self.api.k.ResumeThread(info.hThread) == 1, 'resume count')
            child['resumed'] = True
            return child
        except BaseException:
            # Do not leave a test process suspended if pre-resume verification failed.
            if not child['resumed']:
                self.api.ok(self.api.k.TerminateProcess(info.hProcess, 0xE2))
                require(self.api.k.WaitForSingleObject(info.hProcess, 5000) == 0, 'owned cleanup timeout')
            raise
        finally:
            self.api.ok(self.api.k.CloseHandle(info.hThread))

    def state(self, child, point, timeout=25):
        path = self.arena.root/'control'/(child['nonce']+'.state.'+point+'.json')
        until = time.monotonic()+timeout
        while time.monotonic() < until:
            if path.exists():
                try:
                    value = json.loads(path.read_bytes())
                except json.JSONDecodeError:
                    time.sleep(.01); continue
                require(value['pid'] == child['pid'] and value['nonce'] == child['nonce'], 'child marker mismatch')
                return value
            if self.api.k.WaitForSingleObject(child['process'], 0) == 0:
                raise RuntimeError('child exited before '+point+': '+str(self.result(child)))
            time.sleep(.01)
        raise RuntimeError('bounded child marker timeout: '+point)

    def release(self, child, point):
        self.arena.write_new('control/'+child['nonce']+'.continue-'+point, b'continue\n')

    def wait(self, child, timeout=10):
        require(self.api.k.WaitForSingleObject(child['process'], int(timeout*1000)) == 0, 'owned child exit timeout')
        require(self.api.creation_time(child['process']) == child['identity']['creation_filetime'], 'process identity changed')
        result = T.DWORD()
        self.api.ok(self.api.k.GetExitCodeProcess(child['process'], ctypes.byref(result)))
        child['exit_code'] = result.value
        return result.value

    def result(self, child):
        path = self.arena.root/'control'/(child['nonce']+'.result.json')
        return json.loads(path.read_bytes()) if path.exists() else None

    def job_pids(self):
        # JOBOBJECT_BASIC_PROCESS_ID_LIST: two DWORDs then ULONG_PTR array.
        buffer = ctypes.create_string_buffer(8 + 16*ctypes.sizeof(ctypes.c_size_t))
        self.api.ok(self.api.k.QueryInformationJobObject(self.handle, 3, buffer, len(buffer), None))
        count = ctypes.cast(ctypes.byref(buffer, 4), ctypes.POINTER(T.DWORD)).contents.value
        require(count <= 16, 'unexpected Job size')
        return set((ctypes.c_size_t*count).from_buffer(buffer, 8))

    def stop(self):
        members = self.job_pids()
        if not members.issubset({c['pid'] for c in self.children}):
            self.arena.write_new('control/membership-HOLD-'+uuid.uuid4().hex+'.json',json.dumps(self.membership_report(),sort_keys=True).encode())
        require(members.issubset({c['pid'] for c in self.children}), 'unidentified Job member: HOLD '+repr(members))
        for child in self.children:
            require(self.api.creation_time(child['process']) == child['identity']['creation_filetime'], 'refuse PID-only stop')
            if child['resumed'] and self.api.k.WaitForSingleObject(child['process'],0)!=0:
                require(self.api.process_identity(child['process']) == child['identity'], 'live image changed')
                require(self.api.in_job(child['process'], self.handle), 'refuse nonowned stop')
        self.api.ok(self.api.k.TerminateJobObject(self.handle, 0xE3))
        for child in self.children:
            self.wait(child)
        require(not self.job_pids(), 'remaining Job processes')

    def membership_report(self):
        rows=[]
        for pid in sorted(self.job_pids()):
            h=self.api.k.OpenProcess(0x1000|0x100000,False,pid)
            if not h:
                rows.append(dict(pid=pid,query='UNAVAILABLE')); continue
            try: rows.append(dict(pid=pid,identity=self.api.process_identity(h)))
            except OSError: rows.append(dict(pid=pid,query='EXITED_OR_UNAVAILABLE'))
            finally: self.api.ok(self.api.k.CloseHandle(h))
        return dict(expected=[c['pid'] for c in self.children],members=rows)

    def review_recovery(self, child, expected_nonce):
        """Read-only ownership proof. Never removes a lock or resumes a writer."""
        self.arena.check()
        require(expected_nonce == child['nonce'], 'explicit owner confirmation required')
        require(sha(self.arena.root/'process-scope.json') == child['request']['scope_sha256'], 'owner marker changed')
        self.wait(child,timeout=0)
        require(not self.job_pids(), 'owner still active')
        lock = self.arena.root/'publication.lock'
        token = json.loads(lock.read_bytes())
        require(token['request_id'] == child['request']['request_id'], 'lock request owner mismatch')
        return dict(root_id=self.arena.root_id,process_identity=child['identity'],nonce=expected_nonce,
                    lock_sha256=sha(lock),owner_exit_verified=True,auto_resume=False,auto_delete=False)

    def close(self):
        if self.closed:
            return
        try:
            if self.job_pids():
                self.stop()  # Only newly created, kernel-verified children.
            for child in self.children:
                self.wait(child)
            require(not self.job_pids(), 'Job not empty at close')
            serial = []
            for child in self.children:
                serial.append({k:v for k,v in child.items() if k != 'process'})
        finally:
            for child in self.children:
                self.api.ok(self.api.k.CloseHandle(child['process']))
            self.api.ok(self.api.k.CloseHandle(self.handle))
            self.closed = True
        self.arena.write_new('control/job-'+self.name.rsplit('.',1)[-1]+'.audit.json',
            json.dumps(dict(job=self.name, children=serial, active_after=0, timeout_cleanup_seconds=10,
                            handles_closed=True), sort_keys=True).encode())


def child_main(request_path):
    """This entrypoint is never a production worker and has no network API."""
    helper = Path(__file__).resolve()
    request_path = Path(request_path).absolute()
    request = json.loads(request_path.read_bytes())
    root = Path(request['root']).absolute()
    require(request_path.parent == root/'control' and request_path.name == request['nonce']+'.request.json', 'request path')
    require(root.name.startswith('j1ai-weekend-staging-'), 'fresh staging name')
    require(sha(helper) == request['helper_sha256'], 'helper changed')
    # Install guards before any project/third-party import. Native operations
    # below are reviewed separately; these hooks are not OS isolation proof.
    def audit(event, args):
        if event.startswith('socket.') or event in {'subprocess.Popen','os.system','os.posix_spawn'}:
            raise RuntimeError('child network/process prohibited: '+event)
        if event == 'import' and args[0].split('.')[0] in {'joblib','sklearn','lightgbm','catboost'}:
            raise RuntimeError('child model import prohibited')
        if event == 'open' and isinstance(args[0], (str,bytes)):
            p = Path(os.fsdecode(args[0])).absolute()
            mode = args[1] or ''
            write = any(c in mode for c in 'wax+') if isinstance(mode,str) else False
            write = write or (len(args)>2 and isinstance(args[2],int) and args[2] & (os.O_WRONLY|os.O_RDWR|os.O_CREAT|os.O_TRUNC))
            if write and not p.is_relative_to(root):
                raise RuntimeError('child write outside dedicated arena')
            if p.is_relative_to(helper.parents[2]) and any(x in {'models','data'} for x in p.parts):
                raise RuntimeError('child production data read prohibited')
        if event in {'os.remove','os.rmdir','os.mkdir','os.rename'}:
            values = args[:2] if event == 'os.rename' else args[:1]
            require(all(not isinstance(v,(str,bytes)) or Path(os.fsdecode(v)).absolute().is_relative_to(root) for v in values), 'child path outside arena')
    sys.addaudithook(audit)
    sys.dont_write_bytecode = True
    sys.path[:0] = [str(helper.parents[1])]
    from src.modeling.weekend_staging_windows import Arena, Windows, identity, publish_staging, read_staging
    require(sha(helper.parents[1]/'src/modeling/weekend_staging_windows.py') == request['storage_sha256'], 'storage changed')
    api = API(); job = api.k.OpenJobObjectW(4, False, request['job'])
    api.ok(job)
    try:
        require(api.in_job(api.k.GetCurrentProcess(),job), 'child not in explicit test Job')
    finally:
        api.ok(api.k.CloseHandle(job))
    native = Windows()
    require(list(identity(root)) == request['root_id'] and native.security(root) == request['acl'], 'arena ownership mismatch')
    require(sha(root/'process-scope.json') == request['scope_sha256'], 'process owner marker changed')
    # Attach only by a parent-issued, pinned, test-only capability. Arena itself
    # still exposes no general attach-to-existing/runtime API.
    h = native.open_directory(root)
    arena = Arena(root,native,h)
    for p in [root,*root.rglob('*')]:
        if p.is_dir(): arena.directories[p] = (identity(p),native.security(p))
    marker = root/'scope.json'; arena.files[marker] = (identity(marker),native.security(marker)); arena.ready = True
    arena.check()
    nonce = request['nonce']
    source = request['source']
    def validate_saved(path):
        # This child validates only the exact byte packet whose full Phase4
        # semantics were checked by the parent. No numpy/updater import occurs.
        require(path.is_relative_to(root),'test packet outside root')
        for p in [path,*path.iterdir()]: identity(p)
        require(source['files']=={p.name:sha(p) for p in path.iterdir()}, 'parent-verified saved packet changed')
        return ([dict(fixture_key=k) for k in source['fixture_keys']],[],{}, {})
    def emit(suffix, data):
        tx=arena.active_transaction
        arena.write_new('control/'+nonce+suffix, json.dumps(dict(pid=os.getpid(),nonce=nonce,
            owned_lock_sha256=hashlib.sha256(tx[3]).hexdigest() if tx else None,**data),sort_keys=True).encode())
    def state(point):
        emit('.state.'+point+'.json', dict(point=point))
        if point in request['pauses']:
            until = time.monotonic()+20
            while not (root/'control'/(nonce+'.continue-'+point)).exists():
                require(time.monotonic() < until, 'child pause deadline')
                time.sleep(.01)
    try:
        state('ready')
        operation = request['operation']
        if operation in {'claim','publish'}:
            with arena.transaction(request['request_id']):
                state('lock-held')
                if operation == 'publish':
                    original = root/source['directory']
                    require(original.is_relative_to(root/'input'), 'synthetic input only')
                    def recheck():
                        require(source['files'] == {p.name:sha(p) for p in original.iterdir()}, 'test saved input changed')
                    recheck()
                    publish_staging(arena,original,request['request_id'],source['witness'],source['model_pins'],
                        set(source['fixture_keys']),validate_saved=validate_saved,recheck=recheck,fault=state)
            emit('.result.json', dict(status='PASS',operation=operation))
        elif operation == 'mutate':
            results = {}
            operations = dict(rename=lambda:(root/'held-rename').rename(root/'renamed'),
                delete=lambda:(root/'held-delete').rmdir(),
                replace=lambda:(root/'replacement').replace(root/'held-replace'),
                file_replace=lambda:(root/'replacement-file').replace(root/'held-file-replace'))
            for name, action in operations.items():
                try: action(); results[name] = dict(allowed=True)
                except OSError as error: results[name] = dict(allowed=False,winerror=error.winerror)
            emit('.result.json', dict(status='PASS',results=results))
        elif operation == 'observe':
            counts, holds = [], 0
            state('observing')
            until = time.monotonic()+20
            while not (root/'control'/(nonce+'.continue-observe')).exists():
                require(time.monotonic() < until, 'observer deadline')
                try:
                    records,_,_,_ = read_staging(arena,request['request_id'],source['model_pins'],validate_saved)
                    counts.append(len(records))
                    if len(counts)==1: state('first-complete')
                except (OSError,ValueError):
                    holds += 1
                    if holds==1: state('first-hold')
                time.sleep(.01)
            emit('.result.json',dict(status='PASS',counts=counts,holds=holds))
        else: raise RuntimeError('unknown child operation')
        return 0
    except BaseException as error:
        emit('.result.json',dict(status='HOLD',error_type=type(error).__name__,reason=str(error)))
        return 3
    finally:
        arena.close()


if __name__ == '__main__':
    require(len(sys.argv)==3 and sys.argv[1]=='--test-child','test-only request required')
    raise SystemExit(child_main(sys.argv[2]))
