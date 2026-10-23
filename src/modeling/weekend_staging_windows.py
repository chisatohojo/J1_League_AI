"""NTFS mock-staging storage. No process, network, model or runtime entrypoint.

Only create-new arenas under system temp are supported. Failed locks/attempts
are evidence, never cleanup targets. This is not an OS sandbox or a power-loss
guarantee. Production activation is deliberately unavailable.
"""
from contextlib import contextmanager
import ctypes
from ctypes import wintypes as T
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
import uuid

STAGING_FORMAT = "weekend-production-staging-envelope-v1"
STAGING_SCOPE = "STAGING_MOCK_ONLY"


class StagingHold(ValueError):
    pass


def need(value, reason):
    if not value:
        raise StagingHold(reason)


def body(value):
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode()


def digest(value):
    return hashlib.sha256(value).hexdigest()


def now():
    return datetime.now(timezone.utc).isoformat()


def read_staging(arena, request_id, model_pins, validate_saved):
    """Storage validation shared by the semantic reader and bounded test child.

    validate_saved is the unchanged Phase4 semantic reader in Publisher. The
    test child instead accepts only parent-verified, byte-pinned synthetic input.
    Neither route can admit this staging envelope into operational history.
    """
    need(type(request_id) is str and re.fullmatch(r'[0-9a-f]{64}',request_id), "request_id")
    root = arena.path("batch-"+request_id)
    need(root.is_dir(), "staging_batch_missing")
    def read(name): return json.loads(arena.path(root.name+"/"+name).read_bytes())
    manifest, receipt, seal = read("staging-manifest.json"), read("receipt.json"), read("seal.json")
    need(set(manifest)=={"format_version","scope","request_id","batch_directory","batch_manifest_sha256","files","model_contract_pins","mock_witness_sha256","production_admission"}
         and manifest["format_version"]==STAGING_FORMAT and manifest["scope"]==STAGING_SCOPE
         and manifest["production_admission"] is False and manifest["request_id"]==request_id, "staging_manifest_contract")
    need(set(receipt)=={"scope","request_id","manifest_sha256","publication_readback_completed_at_utc","production_admission","power_loss_verified","process_crash_verified"}
         and receipt["scope"]==STAGING_SCOPE and receipt["request_id"]==request_id
         and receipt["manifest_sha256"]==digest(body(manifest)) and receipt["production_admission"] is False
         and receipt["power_loss_verified"] is False and receipt["process_crash_verified"] is False, "staging_receipt_contract")
    need(seal==dict(scope=STAGING_SCOPE,request_id=request_id,receipt_sha256=digest(body(receipt)),readback=True), "staging_seal_contract")
    child = arena.path(root.name+"/"+manifest["batch_directory"])
    need(manifest["batch_directory"]=="weekend-v2-source-"+manifest["batch_manifest_sha256"], "inner_batch_identity")
    need(set(p.name for p in root.iterdir())=={child.name,"staging-manifest.json","receipt.json","seal.json"}, "envelope_files")
    result = validate_saved(child)
    need(manifest["files"]=={p.name:digest(p.read_bytes()) for p in child.iterdir()}
         and digest((child/"manifest.json").read_bytes())==manifest["batch_manifest_sha256"]
         and manifest["model_contract_pins"]==model_pins, "staging_payload_changed")
    arena.check()
    return result


def publish_staging(arena, original, request_id, witness, model_pins, fixture_keys, *, validate_saved, recheck, fault):
    """Existing envelope I/O extracted unchanged from Publisher, not a new E2E.

    Only a live owned transaction can copy a previously validated synthetic
    batch. Caller supplies the semantic verifier; no model/updater imports here.
    """
    arena.require_transaction(request_id)
    validate_saved(original)
    for existing in arena.root.glob("batch-*"):
        previous, _, _, _ = read_staging(arena,existing.name[6:],model_pins,validate_saved)
        need(not fixture_keys.intersection(row["fixture_key"] for row in previous), "duplicate_saved_fixture")
    need(type(witness) is str and re.fullmatch(r'[0-9a-f]{64}',witness), "mock_witness_sha256")
    pins = {p.name:digest(p.read_bytes()) for p in original.iterdir()}
    pending = "pending-"+uuid.uuid4().hex
    arena.mkdir(pending); arena.mkdir(pending+"/"+original.name)
    for name, expected in pins.items():
        data = (original/name).read_bytes()
        need(digest(data)==expected, "saved_batch_changed")
        arena.write_new(pending+"/"+original.name+"/"+name,data)
        fault("after_"+name)
    manifest = dict(format_version=STAGING_FORMAT,scope=STAGING_SCOPE,request_id=request_id,
        batch_directory=original.name,batch_manifest_sha256=pins["manifest.json"],files=pins,
        model_contract_pins=dict(model_pins),mock_witness_sha256=witness,production_admission=False)
    arena.write_new(pending+"/staging-manifest.json",body(manifest))
    validate_saved(arena.path(pending+"/"+original.name))
    need(pins=={p.name:digest(p.read_bytes()) for p in original.iterdir()}, "saved_batch_changed")
    recheck(); arena.require_transaction(request_id); fault("before_rename")
    destination = "batch-"+request_id
    arena.rename_new(pending,destination); fault("after_rename")
    validate_saved(arena.path(destination+"/"+original.name))
    receipt = dict(scope=STAGING_SCOPE,request_id=request_id,manifest_sha256=digest(body(manifest)),
        publication_readback_completed_at_utc=now(),production_admission=False,power_loss_verified=False,process_crash_verified=False)
    fault("before_receipt"); arena.write_new(destination+"/receipt.json",body(receipt))
    fault("before_seal"); arena.write_new(destination+"/seal.json",body(dict(scope=STAGING_SCOPE,
        request_id=request_id,receipt_sha256=digest(body(receipt)),readback=True)))
    read_staging(arena,request_id,model_pins,validate_saved); fault("after_seal")
    return destination


class Windows:
    def __init__(self):
        need(os.name == "nt", "windows_required")
        self.k = ctypes.WinDLL("kernel32", use_last_error=True)
        self.a = ctypes.WinDLL("advapi32", use_last_error=True)
        self.k.CreateFileW.argtypes = [T.LPCWSTR, T.DWORD, T.DWORD, T.LPVOID, T.DWORD, T.DWORD, T.HANDLE]
        self.k.CreateFileW.restype = T.HANDLE
        self.k.CloseHandle.argtypes = [T.HANDLE]
        self.k.CloseHandle.restype = T.BOOL
        self.k.FlushFileBuffers.argtypes = [T.HANDLE]
        self.k.FlushFileBuffers.restype = T.BOOL
        self.k.WriteFile.argtypes = [T.HANDLE, T.LPCVOID, T.DWORD, ctypes.POINTER(T.DWORD), T.LPVOID]
        self.k.WriteFile.restype = T.BOOL
        self.k.ReadFile.argtypes = [T.HANDLE, T.LPVOID, T.DWORD, ctypes.POINTER(T.DWORD), T.LPVOID]
        self.k.ReadFile.restype = T.BOOL
        self.k.SetFilePointerEx.argtypes = [T.HANDLE, ctypes.c_longlong, T.LPVOID, T.DWORD]
        self.k.SetFilePointerEx.restype = T.BOOL
        self.k.SetFileInformationByHandle.argtypes = [T.HANDLE, T.DWORD, T.LPVOID, T.DWORD]
        self.k.SetFileInformationByHandle.restype = T.BOOL
        self.k.GetVolumePathNameW.argtypes = [T.LPCWSTR, T.LPWSTR, T.DWORD]
        self.k.GetVolumeInformationW.argtypes = [T.LPCWSTR, T.LPWSTR, T.DWORD, ctypes.POINTER(T.DWORD), ctypes.POINTER(T.DWORD), ctypes.POINTER(T.DWORD), T.LPWSTR, T.DWORD]
        self.k.LocalFree.argtypes = [T.HLOCAL]
        self.k.LocalFree.restype = T.HLOCAL
        self.a.GetNamedSecurityInfoW.argtypes = [T.LPWSTR, T.DWORD, T.DWORD, ctypes.POINTER(T.LPVOID), ctypes.POINTER(T.LPVOID), ctypes.POINTER(T.LPVOID), ctypes.POINTER(T.LPVOID), ctypes.POINTER(T.LPVOID)]
        self.a.GetNamedSecurityInfoW.restype = T.DWORD
        self.a.ConvertSecurityDescriptorToStringSecurityDescriptorW.argtypes = [T.LPVOID, T.DWORD, T.DWORD, ctypes.POINTER(T.LPWSTR), ctypes.POINTER(T.DWORD)]
        self.a.ConvertSidToStringSidW.argtypes = [T.LPVOID, ctypes.POINTER(T.LPWSTR)]
        self.a.ConvertStringSecurityDescriptorToSecurityDescriptorW.argtypes = [T.LPCWSTR, T.DWORD, ctypes.POINTER(T.LPVOID), ctypes.POINTER(T.DWORD)]
        self.a.SetFileSecurityW.argtypes = [T.LPCWSTR, T.DWORD, T.LPVOID]

    def ok(self, value):
        if not value:
            raise ctypes.WinError(ctypes.get_last_error())

    def open_directory(self, path):
        # No FILE_SHARE_DELETE: the owned directory cannot be replaced while held.
        # READ_CONTROL alone does not participate in delete-sharing checks.
        # Request GENERIC_READ as well; the negative control must prove refusal.
        h = self.k.CreateFileW(str(path), 0x80020000, 3, None, 3, 0x02200000, None)
        if h == ctypes.c_void_p(-1).value:
            raise ctypes.WinError(ctypes.get_last_error())
        return h

    def security(self, path):
        sd, owner, dacl = T.LPVOID(), T.LPVOID(), T.LPVOID()
        result = self.a.GetNamedSecurityInfoW(str(path), 1, 5, ctypes.byref(owner), None, ctypes.byref(dacl), None, ctypes.byref(sd))
        if result:
            raise ctypes.WinError(result)
        text, sid = T.LPWSTR(), T.LPWSTR()
        try:
            need(bool(owner) and bool(dacl), "owner_or_DACL_missing")
            self.ok(self.a.ConvertSecurityDescriptorToStringSecurityDescriptorW(sd, 1, 5, ctypes.byref(text), None))
            self.ok(self.a.ConvertSidToStringSidW(owner, ctypes.byref(sid)))
            return dict(owner=sid.value, sddl=text.value)
        finally:
            for value in (text, sid, sd):
                if value:
                    self.k.LocalFree(value)

    def restrict_new_directory(self, path):
        # Caller supplies only its just-created arena, never an existing root.
        sid = self.security(path)["owner"]
        sd = T.LPVOID()
        self.ok(self.a.ConvertStringSecurityDescriptorToSecurityDescriptorW(
            f"D:P(A;OICI;FA;;;{sid})(A;OICI;FA;;;SY)", 1, ctypes.byref(sd), None))
        try:
            self.ok(self.a.SetFileSecurityW(str(path), 0x80000004, sd))
        finally:
            self.k.LocalFree(sd)

    def filesystem(self, path):
        volume, fs = ctypes.create_unicode_buffer(32768), ctypes.create_unicode_buffer(64)
        self.ok(self.k.GetVolumePathNameW(str(path), volume, len(volume)))
        self.ok(self.k.GetVolumeInformationW(volume.value, None, 0, None, None, None, fs, len(fs)))
        return fs.value

    def claim(self, path, data):
        h = self.k.CreateFileW(str(path), 0xC0010000, 0, None, 1, 0x80000000, None)
        if h == ctypes.c_void_p(-1).value:
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            count = T.DWORD()
            self.ok(self.k.WriteFile(h, data, len(data), ctypes.byref(count), None))
            need(count.value == len(data), "short_lock_write")
            self.ok(self.k.FlushFileBuffers(h))
            return h
        except BaseException:
            self.k.CloseHandle(h)
            raise

    def delete_owned_lock_on_close(self, handle, path, token, file_id):
        # Verify and delete via the still-exclusive handle, not a pathname race
        # after close. DELETE was requested only for this CREATE_NEW lock file.
        self.verify_owned_lock(handle, path, token, file_id)
        delete = T.BYTE(1)  # FILE_DISPOSITION_INFO.DeleteFile is BOOLEAN, not BOOL.
        self.ok(self.k.SetFileInformationByHandle(handle, 4, ctypes.byref(delete), ctypes.sizeof(delete)))

    def verify_owned_lock(self, handle, path, token, file_id):
        need(identity(path) == file_id, "lock_identity_changed")
        self.ok(self.k.SetFilePointerEx(handle, 0, None, 0))
        buffer, count = ctypes.create_string_buffer(len(token)+1), T.DWORD()
        self.ok(self.k.ReadFile(handle, buffer, len(token)+1, ctypes.byref(count), None))
        need(buffer.raw[:count.value] == token, "lock_owner_changed")


def identity(path):
    info = path.lstat()
    need(not (getattr(info, "st_file_attributes", 0) & 0x400), "reparse_point")
    return info.st_dev, info.st_ino


class Arena:
    """One temporary, ACL-protected NTFS arena. No attach-to-existing API."""
    def __init__(self, root, api, handle):
        self.root, self.api, self.handle = root, api, handle
        self.root_id, self.acl = identity(root), api.security(root)
        self.directories = {root: (self.root_id, self.acl)}
        self.files = {}
        self.ready = False
        self.active_transaction = None

    @classmethod
    def create(cls, path):
        api = Windows()
        root = Path(path).absolute()
        base = Path(tempfile.gettempdir()).resolve()
        need(root.parent.resolve() == base and not root.exists(), "exclusive_system_temp_arena_required")
        for part in (root.parent, *root.parent.parents):
            identity(part)
        need(api.filesystem(root.parent) == "NTFS", "NTFS_required")
        root.mkdir()
        handle = api.open_directory(root)
        try:
            identity(root)  # Reject replacement before changing the NEW root ACL.
            api.restrict_new_directory(root)
            arena = cls(root, api, handle)
            arena.write_new("scope.json", body(dict(scope="STAGING_MOCK_ONLY", production_enabled=False)))
            arena.ready = True
            arena.check()
            return arena
        except BaseException:
            api.ok(api.k.CloseHandle(handle))
            raise

    def close(self):
        if self.handle is not None:
            self.api.ok(self.api.k.CloseHandle(self.handle))
            self.handle = None

    def check(self):
        need(self.handle is not None and identity(self.root) == self.root_id, "arena_identity_changed_or_closed")
        need(self.api.security(self.root) == self.acl, "arena_owner_or_DACL_changed")
        if self.ready:
            marker = self.root / "scope.json"
            need((identity(marker), self.api.security(marker)) == self.files[marker]
                 and marker.read_bytes() == body(dict(scope="STAGING_MOCK_ONLY",production_enabled=False)),
                 "arena_scope_changed")

    def path(self, relative):
        self.check()
        need(type(relative) is str and len(relative) <= 512, "relative_path_required")
        parts = relative.split("/")
        for item in parts:
            need(re.fullmatch(r"[A-Za-z0-9_.-]{1,128}", item) and item not in {".", ".."}
                 and item.split(".")[0].upper() not in {"CON", "PRN", "AUX", "NUL", *{f"COM{i}" for i in range(1,10)}, *{f"LPT{i}" for i in range(1,10)}}, "unsafe_relative_path")
        out = self.root.joinpath(*parts)
        for parent in (out, *out.parents):
            if parent.exists() or parent.is_symlink():
                identity(parent)
                expected = self.directories.get(parent, self.files.get(parent))
                if expected is not None:
                    need((identity(parent), self.api.security(parent)) == expected, "saved_identity_owner_or_DACL_changed")
            if parent == self.root:
                break
        return out

    @contextmanager
    def parents(self, path):
        held = []
        try:
            parents = []
            p = path.parent
            while p != self.root:
                parents.append(p)
                p = p.parent
            for p in reversed(parents):
                need(p in self.directories and (identity(p), self.api.security(p)) == self.directories[p],
                     "parent_identity_owner_or_DACL_changed")
                held.append(self.api.open_directory(p))
                need((identity(p), self.api.security(p)) == self.directories[p], "parent_changed_during_open")
            yield
            self.check()
        finally:
            for h in reversed(held):
                self.api.ok(self.api.k.CloseHandle(h))

    def mkdir(self, relative):
        path = self.path(relative)
        with self.parents(path):
            path.mkdir()
            self.directories[path] = (identity(path), self.api.security(path))
        return path

    def write_new(self, relative, data):
        need(type(data) is bytes and len(data) <= 24*1024*1024, "bounded_bytes_required")
        path = self.path(relative)
        with self.parents(path):
            with path.open("x+b") as stream:
                stream.write(data); stream.flush(); os.fsync(stream.fileno())
                stream.seek(0)
                need(stream.read() == data, "write_readback_failed")
                info = os.fstat(stream.fileno())
                need(identity(path) == (info.st_dev, info.st_ino), "written_file_replaced")
            identity(path)
            security = self.api.security(path)
            self.files[path] = (identity(path), security)
            return dict(sha256=digest(data), bytes=len(data), saved_at_utc=now(), security=security)

    @contextmanager
    def transaction(self, request_id):
        need(re.fullmatch(r"[0-9a-f]{64}", request_id) is not None, "request_id")
        lock = self.path("publication.lock")
        token = body(dict(request_id=request_id, nonce=uuid.uuid4().hex, started_at_utc=now()))
        h = self.api.claim(lock, token)
        lock_id = identity(lock)
        success = False
        try:
            self.write_new("attempt-"+request_id+".json", token)
            self.active_transaction = (request_id, h, lock, token, lock_id)
            yield
            self.check()
            success = True
        finally:
            try:
                # Failed runs keep the original lock/intent; successful deletion
                # targets only the owned kernel handle while it is exclusive.
                if success:
                    self.api.delete_owned_lock_on_close(h, lock, token, lock_id)
            finally:
                self.active_transaction = None
                self.api.ok(self.api.k.CloseHandle(h))

    def require_transaction(self, request_id):
        self.check()
        tx = self.active_transaction
        need(tx is not None and tx[0] == request_id, "owned_transaction_required")
        self.api.verify_owned_lock(*tx[1:])

    def rename_new(self, source_name, destination_name):
        src, dst = self.path(source_name), self.path(destination_name)
        need(src.is_dir() and not dst.exists(), "rename_collision_or_source_missing")
        before = identity(src)
        with self.parents(src), self.parents(dst):
            src.rename(dst)
            need(identity(dst) == before, "directory_identity_changed")
        renamed = {dst/p.relative_to(src): value for p,value in self.directories.items() if p.is_relative_to(src)}
        self.directories = {p:value for p,value in self.directories.items() if not p.is_relative_to(src)} | renamed
        files = {dst/p.relative_to(src): value for p,value in self.files.items() if p.is_relative_to(src)}
        self.files = {p:value for p,value in self.files.items() if not p.is_relative_to(src)} | files
        return dst
