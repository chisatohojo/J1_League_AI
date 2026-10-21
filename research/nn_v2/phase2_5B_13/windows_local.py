"""Windows-only research primitives: owned jobs, protected ACLs and pinned paths.

No sockets, HTTP, permits, collectors, tasks or model APIs.
"""
import ctypes as C
from ctypes import wintypes as W
import hashlib
import os
from pathlib import Path
import subprocess
import sys
import time

if os.name != 'nt':
    raise RuntimeError('Windows OS verification required')
K=C.WinDLL('kernel32',use_last_error=True)
A=C.WinDLL('advapi32',use_last_error=True)
P=C.c_void_p
SIZE=C.c_size_t


def api(lib,name,args,restype=W.BOOL):
    f=getattr(lib,name);f.argtypes=args;f.restype=restype;return f


Close=api(K,'CloseHandle',[W.HANDLE])
CreateFile=api(K,'CreateFileW',[W.LPCWSTR,W.DWORD,W.DWORD,P,W.DWORD,W.DWORD,W.HANDLE],W.HANDLE)
Flush=api(K,'FlushFileBuffers',[W.HANDLE])
Write=api(K,'WriteFile',[W.HANDLE,P,W.DWORD,C.POINTER(W.DWORD),P])
Read=api(K,'ReadFile',[W.HANDLE,P,W.DWORD,C.POINTER(W.DWORD),P])
Seek=api(K,'SetFilePointerEx',[W.HANDLE,C.c_longlong,C.POINTER(C.c_longlong),W.DWORD])
Wait=api(K,'WaitForSingleObject',[W.HANDLE,W.DWORD],W.DWORD)
KillProcess=api(K,'TerminateProcess',[W.HANDLE,W.UINT])
GetExit=api(K,'GetExitCodeProcess',[W.HANDLE,C.POINTER(W.DWORD)])
Resume=api(K,'ResumeThread',[W.HANDLE],W.DWORD)
GetImage=api(K,'QueryFullProcessImageNameW',[W.HANDLE,W.DWORD,W.LPWSTR,C.POINTER(W.DWORD)])
GetTimes=api(K,'GetProcessTimes',[W.HANDLE,C.POINTER(W.FILETIME),C.POINTER(W.FILETIME),C.POINTER(W.FILETIME),C.POINTER(W.FILETIME)])
GetCurrent=api(K,'GetCurrentProcess',[],W.HANDLE)
GetPID=api(K,'GetProcessId',[W.HANDLE],W.DWORD)
GetToken=api(A,'OpenProcessToken',[W.HANDLE,W.DWORD,C.POINTER(W.HANDLE)])
TokenInfo=api(A,'GetTokenInformation',[W.HANDLE,C.c_int,P,W.DWORD,C.POINTER(W.DWORD)])
SidText=api(A,'ConvertSidToStringSidW',[P,C.POINTER(W.LPWSTR)])
LocalFree=api(K,'LocalFree',[P],P)
Security=api(A,'GetNamedSecurityInfoW',[W.LPWSTR,C.c_int,W.DWORD,C.POINTER(P),C.POINTER(P),C.POINTER(P),C.POINTER(P),C.POINTER(P)],W.DWORD)
GetAce=api(A,'GetAce',[P,W.DWORD,C.POINTER(P)])
SDDL=api(A,'ConvertStringSecurityDescriptorToSecurityDescriptorW',[W.LPCWSTR,W.DWORD,C.POINTER(P),C.POINTER(W.DWORD)])
CreateDir=api(K,'CreateDirectoryW',[W.LPCWSTR,P])


def checked(ok,label):
    if not ok:raise OSError(C.get_last_error(),label)
    return ok


def sid_text(pointer):
    text=W.LPWSTR();checked(SidText(pointer,C.byref(text)),'SID conversion')
    try:return text.value
    finally:LocalFree(C.cast(text,P))


def current_sid():
    token=W.HANDLE();checked(GetToken(GetCurrent(),8,C.byref(token)),'Open token')
    try:
        size=W.DWORD();TokenInfo(token,1,None,0,C.byref(size))
        buf=C.create_string_buffer(size.value);checked(TokenInfo(token,1,buf,size,C.byref(size)),'Token user')
        return sid_text(C.cast(buf,C.POINTER(P))[0])
    finally:Close(token)


class ACL(C.Structure):
    _fields_=[('revision',W.BYTE),('reserved',W.BYTE),('size',W.WORD),('count',W.WORD),('reserved2',W.WORD)]


def acl_audit(path):
    owner=P();dacl=P();sd=P()
    result=Security(str(path),1,5,C.byref(owner),None,C.byref(dacl),None,C.byref(sd))
    if result:raise OSError(result,'Get file security')
    try:
        if not dacl.value:raise ValueError('NULL_DACL_FORBIDDEN')
        entries=[]
        for i in range(C.cast(dacl,C.POINTER(ACL)).contents.count):
            ace=P();checked(GetAce(dacl,i,C.byref(ace)),'Read ACE')
            typ=C.cast(ace,C.POINTER(W.BYTE))[0]
            if typ!=0:raise ValueError('UNREVIEWED_ACE_TYPE')
            mask=C.cast(ace.value+4,C.POINTER(W.DWORD))[0]
            entries.append({'sid':sid_text(ace.value+8),'mask':mask})
        who=sid_text(owner);allowed={current_sid(),'S-1-5-18','S-1-5-32-544'}
        if who!=current_sid() or {e['sid'] for e in entries}!=allowed:
            raise ValueError('OWNER_OR_DACL_SCOPE_MISMATCH')
        if any(e['mask']&0x1f01ff!=0x1f01ff for e in entries):raise ValueError('RESTRICTED_ROOT_ACCESS_MISMATCH')
        return {'owner_sid':who,'allowed_aces':entries,'scope_verified':True}
    finally:LocalFree(sd)


class SA(C.Structure):
    _fields_=[('length',W.DWORD),('descriptor',P),('inherit',W.BOOL)]


def secure_mkdir(path):
    sid=current_sid();sd=P();length=W.DWORD()
    policy=f'O:{sid}D:P(A;OICI;FA;;;{sid})(A;OICI;FA;;;SY)(A;OICI;FA;;;BA)'
    checked(SDDL(policy,1,C.byref(sd),C.byref(length)),'SDDL')
    try:
        sa=SA(C.sizeof(SA),sd,False)
        checked(CreateDir(str(path),C.byref(sa)),'Exclusive protected directory creation')
    finally:LocalFree(sd)
    return acl_audit(path)


class FileInfo(C.Structure):
    _fields_=[('attributes',W.DWORD),('created',W.FILETIME),('accessed',W.FILETIME),('modified',W.FILETIME),
              ('volume',W.DWORD),('size_high',W.DWORD),('size_low',W.DWORD),('links',W.DWORD),('index_high',W.DWORD),('index_low',W.DWORD)]

Info=api(K,'GetFileInformationByHandle',[W.HANDLE,C.POINTER(FileInfo)])


def file_info(handle):
    i=FileInfo();checked(Info(handle,C.byref(i)),'File identity')
    if i.attributes&1024:raise ValueError('REPARSE_POINT_FORBIDDEN')
    return {'volume':i.volume,'index':(i.index_high<<32)|i.index_low,'attributes':i.attributes,
            'bytes':(i.size_high<<32)|i.size_low}


def open_handle(path,access,share,creation,directory=False):
    h=CreateFile(str(path),access,share,None,creation,0x00200000|(0x02000000 if directory else 0x80),None)
    if h==P(-1).value:raise OSError(C.get_last_error(),'Open pinned path')
    try:file_info(h)
    except BaseException:Close(h);raise
    return h


class DirectoryLease:
    """Open ancestor directories without FILE_SHARE_DELETE, preventing substitution."""
    def __init__(self,path):
        self.path=Path(os.path.abspath(path));self.handles=[];self.identities=[]
        try:
            for p in [*reversed(self.path.parents),self.path]:
                # Attribute-only handles are exempt from relevant sharing checks.
                # GENERIC_READ makes omission of FILE_SHARE_DELETE effective.
                h=open_handle(p,0x80000000,3,3,True)
                self.handles.append(h);self.identities.append({'path':str(p),**file_info(h)})
        except BaseException:self.close();raise

    def close(self):
        for h in reversed(self.handles):Close(h)
        self.handles=[]

    def __enter__(self):return self
    def __exit__(self,*args):self.close()


def read_bytes_locked(path,cap=8*1024*1024):
    with DirectoryLease(Path(path).parent):
        h=open_handle(path,0x80000000,1,3)
        try:
            info=file_info(h)
            if info['bytes']>cap:raise ValueError('LOCAL_BYTE_CAP')
            parts=[];remaining=info['bytes']
            while remaining:
                buf=C.create_string_buffer(min(65536,remaining));n=W.DWORD()
                checked(Read(h,buf,len(buf),C.byref(n),None),'Read held file')
                if not n.value:raise ValueError('INCOMPLETE_HELD_READ')
                parts.append(buf.raw[:n.value]);remaining-=n.value
            return b''.join(parts)
        finally:Close(h)


def write_new_locked(path,data):
    with DirectoryLease(Path(path).parent):
        h=open_handle(path,0xc0000000,0,1)
        try:
            offset=0
            while offset<len(data):
                part=data[offset:offset+65536];n=W.DWORD();buf=C.create_string_buffer(part)
                checked(Write(h,buf,len(part),C.byref(n),None),'Write exclusive held file')
                if not n.value:raise ValueError('SHORT_WRITE')
                offset+=n.value
            checked(Flush(h),'FlushFileBuffers')
            checked(Seek(h,0,None,0),'Seek readback')
            chunks=[];left=len(data)
            while left:
                buf=C.create_string_buffer(min(left,65536));n=W.DWORD()
                checked(Read(h,buf,len(buf),C.byref(n),None),'Held readback')
                if not n.value:raise ValueError('SHORT_READBACK')
                chunks.append(buf.raw[:n.value]);left-=n.value
            if b''.join(chunks)!=data:raise ValueError('READBACK_MISMATCH')
            return {'SHA256':hashlib.sha256(data).hexdigest(),'bytes':len(data),'identity':file_info(h),'FlushFileBuffers':True}
        finally:Close(h)


class Startup(C.Structure):
    _fields_=[('cb',W.DWORD),('reserved',W.LPWSTR),('desktop',W.LPWSTR),('title',W.LPWSTR),
      ('x',W.DWORD),('y',W.DWORD),('xs',W.DWORD),('ys',W.DWORD),('xc',W.DWORD),('yc',W.DWORD),('fill',W.DWORD),
      ('flags',W.DWORD),('show',W.WORD),('reserved2n',W.WORD),('reserved2',P),('stdin',W.HANDLE),('stdout',W.HANDLE),('stderr',W.HANDLE)]
class ProcessInfo(C.Structure):
    _fields_=[('process',W.HANDLE),('thread',W.HANDLE),('pid',W.DWORD),('tid',W.DWORD)]
class BasicLimit(C.Structure):
    _fields_=[('process_time',C.c_longlong),('job_time',C.c_longlong),('flags',W.DWORD),('min_ws',SIZE),('max_ws',SIZE),
      ('active_limit',W.DWORD),('affinity',SIZE),('priority',W.DWORD),('scheduling',W.DWORD)]
class IO(C.Structure):_fields_=[(n,C.c_ulonglong) for n in ['read_ops','write_ops','other_ops','read_bytes','write_bytes','other_bytes']]
class ExtendedLimit(C.Structure):
    _fields_=[('basic',BasicLimit),('io',IO),('process_mem',SIZE),('job_mem',SIZE),('peak_process',SIZE),('peak_job',SIZE)]
class Accounting(C.Structure):
    _fields_=[('user',C.c_longlong),('kernel',C.c_longlong),('period_user',C.c_longlong),('period_kernel',C.c_longlong),
      ('faults',W.DWORD),('total_processes',W.DWORD),('active',W.DWORD),('terminated',W.DWORD)]
CreateJob=api(K,'CreateJobObjectW',[P,W.LPCWSTR],W.HANDLE)
SetJob=api(K,'SetInformationJobObject',[W.HANDLE,C.c_int,P,W.DWORD])
QueryJob=api(K,'QueryInformationJobObject',[W.HANDLE,C.c_int,P,W.DWORD,P])
Assign=api(K,'AssignProcessToJobObject',[W.HANDLE,W.HANDLE])
InJob=api(K,'IsProcessInJob',[W.HANDLE,W.HANDLE,C.POINTER(W.BOOL)])
KillJob=api(K,'TerminateJobObject',[W.HANDLE,W.UINT])
CreateProcess=api(K,'CreateProcessW',[W.LPCWSTR,W.LPWSTR,P,P,W.BOOL,W.DWORD,P,W.LPCWSTR,C.POINTER(Startup),C.POINTER(ProcessInfo)])


def process_identity(handle):
    buf=C.create_unicode_buffer(32768);length=W.DWORD(len(buf))
    checked(GetImage(handle,0,buf,C.byref(length)),'Executable identity')
    values=[W.FILETIME() for _ in range(4)];checked(GetTimes(handle,*[C.byref(v) for v in values]),'Process creation identity')
    class BasicProcess(C.Structure):
        _fields_=[('reserved',P),('peb',P),('reserved2',P*2),('pid',SIZE),('parent',SIZE)]
    query=api(C.WinDLL('ntdll'),'NtQueryInformationProcess',[W.HANDLE,C.c_int,P,W.ULONG,C.POINTER(W.ULONG)],W.LONG)
    basic=BasicProcess();size=W.ULONG()
    status=query(handle,0,C.byref(basic),C.sizeof(basic),C.byref(size))
    if status!=0 or basic.pid!=GetPID(handle):raise ValueError('KERNEL_PROCESS_IDENTITY_UNPROVEN')
    return {'executable':buf.value,'executable_SHA256':hashlib.sha256(read_bytes_locked(buf.value)).hexdigest(),
            'creation_FILETIME':(values[0].dwHighDateTime<<32)|values[0].dwLowDateTime,
            'kernel_PID':basic.pid,'kernel_parent_PID':basic.parent}


class OwnedJob:
    """Assign a suspended Python worker to a kill-on-close job before resuming."""
    def __init__(self):
        self.job=CreateJob(None,None);checked(self.job,'Create owned Job Object')
        self.process=None;self.pid=None
        limits=ExtendedLimit();limits.basic.flags=0x2000|8;limits.basic.active_limit=4
        try:checked(SetJob(self.job,9,C.byref(limits),C.sizeof(limits)),'Kill-on-close job limits')
        except BaseException:Close(self.job);self.job=None;raise

    def start(self,arguments,cwd):
        if self.process is not None:raise ValueError('JOB_SINGLE_LAUNCH_ONLY')
        executable=sys._base_executable
        command=C.create_unicode_buffer(subprocess.list2cmdline([executable,*map(str,arguments)]))
        si=Startup();si.cb=C.sizeof(si);si.flags=1;si.show=0;pi=ProcessInfo()
        checked(CreateProcess(executable,command,None,None,False,0x08000000|4,None,str(cwd),C.byref(si),C.byref(pi)), 'Create suspended local worker')
        self.process=pi.process;self.pid=pi.pid
        try:
            checked(Assign(self.job,self.process),'Assign suspended worker to owned job')
            membership=W.BOOL();checked(InJob(self.process,self.job,C.byref(membership)),'Job membership')
            if not membership.value:raise ValueError('OWNERSHIP_NOT_PROVEN')
            identity=process_identity(self.process)
            if identity['kernel_PID']!=self.pid or identity['kernel_parent_PID']!=os.getpid():raise ValueError('KERNEL_PARENT_OWNERSHIP_MISMATCH')
            if str(Path(identity['executable']).resolve()).casefold()!=str(Path(executable).resolve()).casefold():raise ValueError('EXECUTABLE_MISMATCH')
            self.identity={'PID':self.pid,'parent_PID':os.getpid(),'job_membership_verified':True,**identity}
            if Resume(pi.thread)==0xffffffff:raise OSError(C.get_last_error(),'Resume owned worker')
            return self.identity
        except BaseException:
            KillProcess(self.process,0xe13);Wait(self.process,2000);raise
        finally:Close(pi.thread)

    def active(self):
        a=Accounting();checked(QueryJob(self.job,1,C.byref(a),C.sizeof(a),None),'Owned job accounting');return a.active

    def wait(self,seconds):
        if seconds<0 or seconds>120:raise ValueError('FINITE_LOCAL_DEADLINE_REQUIRED')
        result=Wait(self.process,int(seconds*1000))
        if result not in (0,258):raise OSError(C.get_last_error(),'Wait owned process')
        code=W.DWORD();checked(GetExit(self.process,C.byref(code)),'Owned exit code')
        return {'timed_out':result==258,'exit_code':code.value,'active_job_processes':self.active()}

    def cleanup(self,seconds=2):
        if seconds<0 or seconds>10:raise ValueError('FINITE_CLEANUP_DEADLINE_REQUIRED')
        checked(KillJob(self.job,0xe13),'Terminate owned job only')
        end=time.monotonic()+seconds
        while time.monotonic()<end:
            if self.active()==0:return {'cleanup_complete':True,'active':0,'deadline_seconds':seconds}
            time.sleep(.01)
        return {'cleanup_complete':False,'active':self.active(),'deadline_seconds':seconds}

    def close(self):
        if self.job:
            try:
                if self.active():self.cleanup(2)
            finally:Close(self.job);self.job=None
        if self.process:Close(self.process);self.process=None

    def __enter__(self):return self
    def __exit__(self,*args):self.close()
