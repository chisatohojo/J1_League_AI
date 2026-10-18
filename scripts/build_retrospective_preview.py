"""Build an isolated display-only preview from saved inputs. No network or prediction."""
import argparse
import csv
from datetime import datetime, timezone
import io
import json
import os
from pathlib import Path

from scripts import build_dashboard_feed as feed
from scripts.dashboard_retrospective import (build_overlay, encoded, read_json,
    read_reconstruction, safe_path, sha)
from src.collect.teams import load_team_master


def write_new(path, body):
    with path.open("xb") as stream:
        stream.write(body)
        stream.flush()
        os.fsync(stream.fileno())
    feed.require(path.read_bytes() == body, "preview_readback")


def csv_body(rows, columns):
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=columns, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode()


def build_preview(source, runtime, retrospective, expected_sha, output, *, now=None):
    source, runtime, retrospective, output = map(safe_path, (source,runtime,retrospective,output))
    for protected in (source,runtime,retrospective,Path(__file__).resolve().parents[1]):
        feed.require(not output.is_relative_to(protected) and not protected.is_relative_to(output), "preview_output_scope")
    feed.require(not output.exists() and not(runtime/"update.lock").exists(), "preview_collision_or_busy")
    pointer_path = runtime/"official/latest.json"
    before = pointer_path.read_bytes()
    pointer = read_json(pointer_path)
    master = load_team_master(source/feed.TEAM_MASTER_PATH)
    official = feed.read_official_revision(runtime/"official/revisions"/pointer["revision_id"],master,
        expected_sha=pointer["manifest_sha256"])
    run, reconstructed = read_reconstruction(retrospective,expected_sha,master)
    for relative,digest in run["source_sha256"].items():
        path=safe_path(source/relative)
        feed.require(path.is_relative_to(source) and sha(path.read_bytes())==digest, "preview_fixed_source_hash")
    records, bindings, batch_pins = [], [], {}
    for directory in sorted((runtime/"batches").iterdir()):
        safe_path(directory)
        feed.require(directory.is_dir() and feed.HEX64.fullmatch(directory.name), "preview_batch_name")
        manifest = read_json(directory/"manifest.json")
        feed.require(set(manifest) == {"predictions.csv","bindings.csv"}, "preview_batch_manifest")
        batch_pins[directory/"manifest.json"] = (directory/"manifest.json").read_bytes()
        for name,digest in manifest.items():
            body=(safe_path(directory/name)).read_bytes()
            feed.require(sha(body)==digest,"preview_saved_hash")
            batch_pins[directory/name] = body
        feed.read_champion_only_predictions(batch_pins[directory/"predictions.csv"])
        records.extend(feed.csv_frame(batch_pins[directory/"predictions.csv"],exact=feed.CHAMPION_COLUMNS).to_dict("records"))
        bindings.extend(feed.csv_frame(batch_pins[directory/"bindings.csv"],exact=feed.BINDING_COLUMNS).to_dict("records"))
    feed.require(len(records)>0 and len(records)==len({r["fixture_key"] for r in records}), "preview_saved_set")
    output.mkdir(parents=True,exist_ok=False)
    prediction,sidecar=output/"saved-predictions.csv",output/"saved-bindings.csv"
    write_new(prediction,csv_body(records,feed.CHAMPION_COLUMNS))
    write_new(sidecar,csv_body(bindings,feed.BINDING_COLUMNS))
    # Existing adapter validates every saved record, witness, binding and fixed model identity.
    dashboard=feed.build_dashboard_feed(source,prediction_file=prediction,binding_file=sidecar,
        official_directory=runtime/"official",champion_only=True,round_view=True,
        now=datetime.now(timezone.utc) if now is None else now)
    saved={r["fixture_key"]:dict(prediction=dict(source="saved_pre_match",generatedAt=r["prediction_generated_at"],
        probabilities={side:float(r[f"a_p_{side}"])*100 for side in ("home","draw","away")})) for r in records}
    names={alias.team_id:alias.canonical_name for alias in master.aliases}
    overlay=build_overlay(dashboard,official,names,saved,run,reconstructed)
    feed.require(pointer_path.read_bytes()==before and all(p.read_bytes()==b for p,b in batch_pins.items())
                 and not(runtime/"update.lock").exists(), "preview_inputs_changed")
    status=dict(state="ready",startedAt=None,finishedAt=None,lastSuccessAt=datetime.now(timezone.utc).isoformat(),errorCode=None)
    for name,value in (("champion_rounds.json",dashboard),("retrospective-overlay.json",overlay),("update-status.json",status)):
        write_new(output/name,encoded(value))
    manifest={p.name:sha(p.read_bytes()) for p in output.iterdir() if p.is_file()}
    write_new(output/"manifest.json",encoded(manifest))
    return dict(output=str(output),official_revision=official.revision_id,run_id=run["run_id"],
        saved_predictions=len(records),overlay_entries=len(overlay["entries"]),diagnostics=overlay["diagnostics"],
        retrospective_sha256=manifest["retrospective-overlay.json"])


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ("source-root","runtime","retrospective","output"):
        parser.add_argument("--"+name,type=Path,required=True)
    parser.add_argument("--retrospective-ledger-sha",required=True)
    args=parser.parse_args(argv)
    try:
        result=build_preview(args.source_root,args.runtime,args.retrospective,args.retrospective_ledger_sha,args.output)
    except (OSError,ValueError,KeyError,TypeError):
        print("Preview build rejected. Inputs were not changed; no demo fallback was used.")
        return 1
    print(json.dumps(result,ensure_ascii=True))
    return 0


if __name__=="__main__":
    raise SystemExit(main())
