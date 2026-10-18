"""Immutable display pairs and one atomic pointer; stdlib-only reader for the launcher."""
from contextlib import contextmanager
from datetime import datetime, timezone
import os
from pathlib import Path
import tempfile

from scripts.retrospective_display import (CHAMPION_HASH, HEX64, checked, encoded, read_json,
    require, safe_path, sha, validate_overlay)
from scripts.serve_dashboard import CHAMPION_MODEL, _object, _timestamp

FILES = {"champion_rounds.json", "retrospective-overlay.json"}
STATUS_KEYS = {"state", "startedAt", "finishedAt", "lastSuccessAt", "errorCode"}


def write_new(path, body):
    with path.open("xb") as stream:
        stream.write(body); stream.flush(); os.fsync(stream.fileno())
    require(path.read_bytes() == body, "generation_readback")


def atomic(path, value):
    safe_path(path)
    fd, name = tempfile.mkstemp(prefix=".publish-", dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(fd,"wb") as stream:
            body=encoded(value);stream.write(body);stream.flush();os.fsync(stream.fileno())
        require(temporary.read_bytes()==body,"generation_readback")
        os.replace(temporary,path)
    finally:
        temporary.unlink(missing_ok=True)


def read_status(root):
    state=read_json(safe_path(root)/"status.json")
    _object(state,STATUS_KEYS,"generation.status")
    require(state["state"] in {"updating","ready","error"} and state["errorCode"] in {None,"update_failed"},"generation_status")
    for key in ("startedAt","finishedAt","lastSuccessAt"):
        if state[key] is not None: _timestamp(state[key],key)
    return state


def contract(overlay, ledger_sha):
    require(isinstance(ledger_sha,str) and HEX64.fullmatch(ledger_sha),"generation_ledger_sha")
    return dict(schemaVersion=1,type="retrospective_display_store",model=dict(CHAMPION_MODEL),
        artifactHash=CHAMPION_HASH,reconstructionRunId=overlay["runId"],
        reconstructionRevision=overlay["reconstructionRevision"],reconstructionLedgerSha256=ledger_sha)


def read_current(root, store_sha):
    root=safe_path(root)
    body=(root/"store.json").read_bytes()
    require(sha(body)==store_sha,"generation_store_sha")
    store=read_json(root/"store.json")
    _object(store,{"schemaVersion","type","model","artifactHash","reconstructionRunId",
        "reconstructionRevision","reconstructionLedgerSha256"},"generation.store")
    require(type(store["schemaVersion"]) is int and store["schemaVersion"]==1
        and store["type"]=="retrospective_display_store" and store["model"]==CHAMPION_MODEL
        and store["artifactHash"]==CHAMPION_HASH,"generation_store")
    for key in ("reconstructionRunId","reconstructionRevision","reconstructionLedgerSha256"):
        require(isinstance(store[key],str) and HEX64.fullmatch(store[key]),"generation_store_hash")
    before=(root/"current.json").read_bytes()
    pointer=read_json(root/"current.json")
    _object(pointer,{"schemaVersion","sequence","generation"},"generation.pointer")
    require(type(pointer["schemaVersion"]) is int and pointer["schemaVersion"]==1
        and type(pointer["sequence"]) is int and 1<=pointer["sequence"]<=2**53-1
        and isinstance(pointer["generation"],str) and HEX64.fullmatch(pointer["generation"]),"generation_pointer")
    directory=safe_path(root/"generations"/pointer["generation"])
    require(directory.parent==root/"generations","generation_scope")
    require({p.name for p in directory.iterdir()}==FILES|{"manifest.json"},"generation_members")
    require(sha((directory/"manifest.json").read_bytes())==pointer["generation"],"generation_manifest_sha")
    manifest=read_json(directory/"manifest.json")
    _object(manifest,{"schemaVersion","sequence","previous","storeSha256","files"},"generation.manifest")
    require(type(manifest["schemaVersion"]) is int and manifest["schemaVersion"]==1
        and type(manifest["sequence"]) is int and manifest["sequence"]==pointer["sequence"]
        and manifest["storeSha256"]==store_sha and isinstance(manifest["files"],dict)
        and set(manifest["files"])==FILES,"generation_manifest")
    previous=manifest["previous"]
    require(previous is None and pointer["sequence"]==1 or isinstance(previous,str)
        and HEX64.fullmatch(previous) and pointer["sequence"]>1,"generation_previous")
    for name,digest in manifest["files"].items(): checked(directory,name,digest)
    dashboard=read_json(directory/"champion_rounds.json")
    overlay=validate_overlay(read_json(directory/"retrospective-overlay.json"),dashboard)
    require(contract(overlay,store["reconstructionLedgerSha256"])==store,"generation_reconstruction_changed")
    require((root/"current.json").read_bytes()==before,"generation_pointer_changed")
    return dict(pointer=pointer,dashboard=dashboard,overlay=overlay,manifest=manifest)


@contextmanager
def publication_lock(root):
    path=root/".publish.lock"
    stream=path.open("x",encoding="ascii")
    try:
        stream.write(str(os.getpid()));stream.flush();os.fsync(stream.fileno());yield
    finally:
        stream.close();path.unlink()


def publish_pair(root,dashboard,overlay,ledger_sha,*,expected_store_sha=None):
    """Old pointer survives every handled failure. Never replace a sealed generation."""
    validate_overlay(overlay,dashboard)
    root=safe_path(root)
    root.mkdir(parents=True,exist_ok=True)
    with publication_lock(root):
        metadata=contract(overlay,ledger_sha)
        if not(root/"store.json").exists():
            require(expected_store_sha is None,"generation_store_missing")
            require(not(root/"current.json").exists(),"generation_incomplete_store")
            write_new(root/"store.json",encoded(metadata))
        store_sha=sha((root/"store.json").read_bytes())
        require((expected_store_sha is None or expected_store_sha==store_sha)
            and read_json(root/"store.json")==metadata,"generation_store_changed")
        (root/"generations").mkdir(exist_ok=True)
        safe_path(root/"generations")
        previous=read_current(root,store_sha) if (root/"current.json").exists() else None
        previous_status=read_status(root) if (root/"status.json").exists() else None
        started=datetime.now(timezone.utc).isoformat()
        state=dict(state="updating",startedAt=started,finishedAt=None,
            lastSuccessAt=previous_status["lastSuccessAt"] if previous_status else None,errorCode=None)
        previous_pointer=previous["pointer"] if previous else None
        committed=False
        try:
            atomic(root/"status.json",state)
            if previous and previous["dashboard"]==dashboard and previous["overlay"]==overlay:
                state.update(state="ready",finishedAt=started,errorCode=None)
                atomic(root/"status.json",state)
                return dict(store_sha256=store_sha,**previous_pointer)
            if previous:
                require(_timestamp(dashboard["updatedAt"],"updatedAt")>=
                    _timestamp(previous["dashboard"]["updatedAt"],"updatedAt"),"generation_publication_rollback")
            sequence=previous_pointer["sequence"]+1 if previous else 1
            bodies={"champion_rounds.json":encoded(dashboard),"retrospective-overlay.json":encoded(overlay)}
            manifest=dict(schemaVersion=1,sequence=sequence,previous=previous_pointer["generation"] if previous else None,
                storeSha256=store_sha,files={name:sha(body) for name,body in bodies.items()})
            generation=sha(encoded(manifest))
            destination=root/"generations"/generation
            if destination.exists():
                safe_path(destination)
                require({p.name for p in destination.iterdir()}==FILES|{"manifest.json"}
                    and (destination/"manifest.json").read_bytes()==encoded(manifest)
                    and all(safe_path(destination/name).read_bytes()==body for name,body in bodies.items()),
                    "generation_existing_bundle_changed")
            else:
                with tempfile.TemporaryDirectory(prefix=".pending-",dir=root/"generations") as temp:
                    stage=Path(temp);require(stage.resolve().parent==root/"generations","generation_stage_scope")
                    bundle=stage/"bundle";bundle.mkdir()
                    for name,body in bodies.items(): write_new(bundle/name,body)
                    write_new(bundle/"manifest.json",encoded(manifest))
                    bundle.rename(destination)
            pointer=dict(schemaVersion=1,sequence=sequence,generation=generation)
            atomic(root/"current.json",pointer);committed=True
            read_current(root,store_sha)
            finished=datetime.now(timezone.utc).isoformat()
            state.update(state="ready",finishedAt=finished,lastSuccessAt=finished)
            atomic(root/"status.json",state)
            return dict(store_sha256=store_sha,**pointer)
        except Exception:
            if committed:
                if previous_pointer: atomic(root/"current.json",previous_pointer)
                else: (root/"current.json").unlink(missing_ok=True)
            state.update(state="error",finishedAt=datetime.now(timezone.utc).isoformat(),errorCode="update_failed")
            atomic(root/"status.json",state)
            raise
