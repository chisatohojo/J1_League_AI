"""Isolated retrospective reconstruction; never a live pre-match prediction lane."""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import csv
import hashlib
import io
import json
import math
import os
from pathlib import Path
import tempfile

import numpy as np
import pandas as pd

from scripts import build_dashboard_feed as feed
from src.collect.teams import load_team_master
from src.modeling import champion_prediction as champion

PREDICTION_TYPE = "retrospective_reconstruction"
OUTCOMES = ("AWAY", "DRAW", "HOME")
HISTORY_COLUMNS = ("match_id", "match_date", "home_team_id", "away_team_id", "result")
P_COLUMNS = ("p_away", "p_draw", "p_home")
DISCLAIMER = (
    "Later retrospective reconstruction, not saved pre-match predictions. "
    "The fixed artifact and selected final publication may postdate these matches. "
    "Historical publication availability is not established; this is not a strict as-of backtest."
)


def utc_now():
    return datetime.now(timezone.utc)


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True, indent=2) + "\n").encode()


def digest(body):
    return hashlib.sha256(body).hexdigest()


def write_new(path, body):
    with Path(path).open("xb") as stream:
        stream.write(body)
        stream.flush()
        os.fsync(stream.fileno())
    feed.require(Path(path).read_bytes() == body, "retrospective_write_readback")


def no_links(path):
    path = Path(path).absolute()
    feed.require(not any(p.is_symlink() or p.is_junction() for p in (path, *path.parents)),
                 "retrospective_link_denied")
    return path.resolve()


@contextmanager
def run_lock(root):
    path = root / ".run.lock"
    stream = path.open("x", encoding="utf-8")
    try:
        stream.write(str(os.getpid()))
        stream.flush()
        os.fsync(stream.fileno())
        yield
    finally:
        stream.close()
        path.unlink()  # Only this invocation's exclusive lock, never another owner.


def source_pins(source):
    pins = {f"{champion.ARTIFACT_PATH}/{name}": value for name, value in champion.FILE_PINS.items()}
    for name, expected in pins.items():
        feed.require(digest(feed.rooted(source, name).read_bytes()) == expected, "champion_bundle_hash")
    metadata = json.loads((source / champion.ARTIFACT_PATH / "metadata.json").read_bytes())
    champion.validate_source_data(source, metadata)
    pins.update({item["path"]: item["sha256"] for item in metadata["source_datasets"]
                 if item["path"] in champion.HISTORY_PATHS})
    pins[champion.HYAKUNEN_PATH] = champion.HYAKUNEN_SHA
    for name, expected in pins.items():
        feed.require(digest(feed.rooted(source, name).read_bytes()) == expected, "retrospective_source_hash")
    return pins


def load_state(source, official, master):
    from src.features.elo_history import _read_hyakunen_matches, _order_matches, _prepare_ongoing_matches
    from src.collect.jleague_hyakunen import validate_competition
    artifact = champion.load_champion(source)  # All frozen hashes pass before deserialization.
    special = _read_hyakunen_matches(source / champion.HYAKUNEN_PATH)
    validate_competition(special)
    special = _order_matches(special, master).loc[:, list(HISTORY_COLUMNS)]
    completed = _prepare_ongoing_matches(official.completed, master, official.observed_at)
    completed["match_date"] = completed.match_date.dt.strftime("%Y-%m-%d")
    return artifact, special, completed


def reconstruct_day(artifact, special, completed, master, targets, day, *, clock=utc_now):
    """Results are stripped from targets; even replay receives strictly earlier rows only."""
    feed.require(tuple(targets.columns) == champion.TARGET_COLUMNS and targets.match_date.eq(day).all(),
                 "retrospective_target_contract")
    history = completed.loc[completed.match_date.lt(day), list(HISTORY_COLUMNS)].copy()
    ratings = champion.replay_ratings(artifact.training, special, history, master, day)
    values = champion.probability_rows(artifact, targets, ratings)
    calculated = feed.timestamp(clock().isoformat()).isoformat()
    rows = []
    for target, probabilities in zip(targets.itertuples(index=False), values):
        home, away = ratings[target.home_team_id], ratings[target.away_team_id]
        rows.append(dict(fixture_key=target.fixture_key, match_id=target.match_id,
            match_date=day, kickoff_time=target.kickoff_time, home_team_id=target.home_team_id,
            away_team_id=target.away_team_id, match_id_namespace=target.match_id_namespace,
            home_elo=float(home), away_elo=float(away), elo_diff=float(home-away),
            **{name: float(probabilities[i]) for i, name in enumerate(P_COLUMNS)},
            prediction_class=int(np.argmax(probabilities)),
            predicted_outcome=OUTCOMES[int(np.argmax(probabilities))],
            tied_maximum=int(np.sum(probabilities == probabilities.max())) > 1,
            calculated_at_utc=calculated, prediction_type=PREDICTION_TYPE,
            model_version=champion.CHAMPION_VERSION, artifact_hash=feed.CHAMPION_HASH,
            model_hash=champion.FILE_PINS["model.joblib"]))
    lineage = dict(target_date=day, history_count=len(history),
        history_max_date=history.match_date.max() if len(history) else None,
        history_sha256=digest(history.sort_values(["match_date", "match_id"]).to_csv(index=False).encode()),
        same_day_results_used=0, future_results_used=0, feature_columns=["elo_diff"])
    return rows, lineage


def publish_bundle(parent, name, bodies):
    destination = parent / name
    feed.require(not destination.exists(), "retrospective_bundle_exists")
    with tempfile.TemporaryDirectory(prefix=".pending-", dir=parent) as temporary:
        stage = Path(temporary)
        # Verify the resolved owned target before TemporaryDirectory's recursive cleanup.
        feed.require(stage.resolve().parent == parent.resolve(), "retrospective_stage_scope")
        bundle = stage / name
        bundle.mkdir()
        for filename, body in bodies.items():
            feed.require(Path(filename).name == filename, "retrospective_bundle_path")
            write_new(bundle / filename, body)
        write_new(bundle / "manifest.json", encoded({filename: digest(body) for filename, body in bodies.items()}))
        bundle.rename(destination)
    return destination


def read_bundle(path, names):
    no_links(path)
    manifest = json.loads((path / "manifest.json").read_bytes())
    feed.require(set(manifest) == set(names) and {p.name for p in path.iterdir()} == set(names) | {"manifest.json"},
                 "retrospective_bundle_members")
    bodies = {}
    for name, expected in manifest.items():
        item = path / name
        no_links(item)
        bodies[name] = item.read_bytes()
        feed.require(digest(bodies[name]) == expected, "retrospective_bundle_hash")
    return bodies


def validate_day(rows, targets, run, day):
    feed.require(len(rows) == len(targets) and len({r["fixture_key"] for r in rows}) == len(rows)
                 and {r["fixture_key"] for r in rows} == set(targets.fixture_key), "retrospective_day_coverage")
    keyed = targets.set_index("fixture_key")
    for row in rows:
        feed.require(row["prediction_type"] == PREDICTION_TYPE and row["run_id"] == run["run_id"]
                     and row["match_date"] == day and row["official_revision"] == run["revision"],
                     "retrospective_day_identity")
        feed.require(not {"result", "home_score", "away_score", "correct", "hit"} & set(row),
                     "retrospective_prediction_contains_outcome")
        original = keyed.loc[row["fixture_key"]]
        feed.require(all(row[key] == original[key] for key in champion.TARGET_COLUMNS
                         if key != "fixture_key"), "retrospective_target_changed")
        values = np.array([row[c] for c in P_COLUMNS], dtype=float)
        feed.require(np.isfinite(values).all() and ((values >= 0) & (values <= 1)).all()
                     and abs(values.sum()-1) <= 1e-12, "retrospective_probabilities")
        feed.require(row["prediction_class"] == int(np.argmax(values))
                     and row["predicted_outcome"] == OUTCOMES[row["prediction_class"]], "retrospective_pick")
        feed.require(row["model_version"] == champion.CHAMPION_VERSION
                     and row["artifact_hash"] == feed.CHAMPION_HASH
                     and row["model_hash"] == champion.FILE_PINS["model.joblib"], "retrospective_model")
        feed.require(feed.timestamp(row["calculated_at_utc"]) >= feed.timestamp(run["official_observed_at"]),
                     "retrospective_calculation_time")
        feed.require(math.isfinite(row["elo_diff"]) and
                     row["elo_diff"] == row["home_elo"]-row["away_elo"], "retrospective_feature")


def metrics(rows):
    if not rows:
        return dict(n=0, hits=0, accuracy=None, log_loss=None, brier_score=None)
    losses, briers = [], []
    for row in rows:
        actual = row["actual_class"]
        values = [row[c] for c in P_COLUMNS]
        losses.append(-math.log(max(values[actual], 1e-15)))
        briers.append(sum((p-int(i == actual))**2 for i, p in enumerate(values)))
    hits = sum(row["correct"] for row in rows)
    return dict(n=len(rows), hits=hits, accuracy=hits/len(rows),
                log_loss=math.fsum(losses)/len(rows), brier_score=math.fsum(briers)/len(rows))


def score_predictions(predictions, official, master):
    """Called only after prediction seals have been flushed and read back."""
    results = official.completed.set_index("fixture_key")
    names = {alias.team_id: alias.canonical_name for alias in master.aliases}
    rows = []
    for prediction in predictions:
        result = results.loc[prediction["fixture_key"]]
        actual = int(result.result)
        rows.append(dict(prediction, round=int(result["round"]),
            home_team=names[prediction["home_team_id"]], away_team=names[prediction["away_team_id"]],
            home_score=int(result.home_score), away_score=int(result.away_score),
            actual_class=actual, actual_outcome=OUTCOMES[actual],
            correct=prediction["prediction_class"] == actual,
            evidence_url=result.evidence_url, evidence_sha256=result.evidence_sha256,
            evidence_fetched_at_utc=result.evidence_fetched_at_utc,
            completion_origin_snapshot=result.completion_origin_snapshot))
    return rows


def csv_body(rows):
    output = io.StringIO(newline="")
    if rows:
        writer = csv.DictWriter(output, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    return output.getvalue().encode("utf-8")


def evaluation_report(rows, run, stage, seal_hash, clock):
    total = metrics(rows)
    expected = (sum(r["match_date"] in run["trial_dates"] for r in run["targets"])
                if stage == "trial" else run["target_count"])
    grouped = {}
    for column in ("match_date", "round", "actual_outcome", "predicted_outcome"):
        keys = sorted({r[column] for r in rows}) if column in {"match_date", "round"} else OUTCOMES
        grouped[column] = {str(key): metrics([r for r in rows if r[column] == key]) for key in keys}
    report = dict(prediction_type=PREDICTION_TYPE, disclaimer=DISCLAIMER, stage=stage,
        run_id=run["run_id"], official_revision=run["revision"], official_observed_at=run["official_observed_at"],
        target_count=expected, run_target_count=run["target_count"], predicted_count=len(rows), pending_count=expected-len(rows),
        coverage=len(rows)/expected, metrics=total, by=grouped,
        probability_scale="0..1", brier_definition="mean sum of squared errors across AWAY/DRAW/HOME (not divided by 3)",
        log_loss_definition="mean -ln(max(p_actual, 1e-15))", tie_policy="first maximum in AWAY,DRAW,HOME class order",
        prediction_seal_sha256=seal_hash, evaluated_at_utc=clock().isoformat())
    lines = ["# Champion A: retrospective reconstruction", "", DISCLAIMER, "",
        f"Official revision: {run['revision']}", f"Stage: {stage}",
        f"Coverage: {len(rows)}/{expected} (full pinned run: {run['target_count']})",
        f"Hits: {total['hits']}/{total['n']}; accuracy: {total['accuracy']:.8%}",
        f"Log Loss: {total['log_loss']:.12f}; multiclass Brier: {total['brier_score']:.12f}", "",
        "Scores and evidence were joined only after the prediction seal was saved.",
        "No live prediction batches, operational feed or tasks were changed.", "",
        "| Round | N | Hits | Accuracy | Log Loss | Brier |", "|---|---:|---:|---:|---:|---:|"]
    for key, value in grouped["round"].items():
        lines.append(f"| {key} | {value['n']} | {value['hits']} | {value['accuracy']:.4%} | {value['log_loss']:.8f} | {value['brier_score']:.8f} |")
    return report, ("\n".join(lines)+"\n").encode()


def prepare_run(source, official_directory, expected_sha, output, *, resume=False):
    source, original, output = no_links(source), no_links(official_directory), no_links(output)
    protected = (source, Path(__file__).resolve().parents[2], original.parents[2])
    feed.require(all(not output.is_relative_to(p) and not p.is_relative_to(output) for p in protected),
                 "retrospective_output_overlaps_inputs")
    pins = source_pins(source)
    master = load_team_master(source / feed.TEAM_MASTER_PATH)
    official = feed.read_official_revision(original, master, expected_sha=expected_sha)
    feed.require(len(official.completed) > 0, "retrospective_no_completed")
    keys = official.completed.sort_values(["match_date", "fixture_key"])[["fixture_key", "match_date"]].to_dict("records")
    days = sorted(official.completed.match_date.unique())
    code_pins = {p.name: digest(p.read_bytes()) for p in (Path(__file__), Path(champion.__file__),
        Path(__file__).parents[1] / "features/elo.py", Path(__file__).parents[1] / "features/elo_history.py")}
    contract = dict(format=1, algorithm="champion-retrospective-v1", prediction_type=PREDICTION_TYPE,
        source_root=str(source), revision=official.revision_id, manifest_sha256=expected_sha,
        source_sha256=pins, code_sha256=code_pins, official_observed_at=official.observed_at,
        target_count=len(keys), targets=keys, dates=days, trial_dates=days[:3], disclaimer=DISCLAIMER)
    identity = digest(encoded(contract))
    contract["run_id"] = identity
    if output.exists():
        feed.require(resume and (output / "run.json").is_file(), "retrospective_resume_required")
        saved = json.loads((output / "run.json").read_bytes())
        feed.require({k: v for k, v in saved.items() if k != "created_at_utc"} == contract,
                     "retrospective_run_contract_changed")
        contract = saved
    else:
        feed.require(not resume, "retrospective_resume_missing")
        output.mkdir(parents=True, exist_ok=False)
        (output / "inputs").mkdir()
        (output / "days").mkdir()
        (output / "prediction-seals").mkdir()
        copied = output / "inputs" / official.revision_id
        copied.mkdir()
        for filename in ("manifest.json", *official.manifest["files"]):
            write_new(copied / filename, (original / filename).read_bytes())
        contract["created_at_utc"] = utc_now().isoformat()
        write_new(output / "run.json", encoded(contract))
    # All future processing reads this immutable copy, not the operational latest pointer.
    official = feed.read_official_revision(output / "inputs" / official.revision_id, master, expected_sha=expected_sha)
    return source, output, official, master, contract


def run_reconstruction(source, official_directory, expected_sha, output, *, stage="trial", resume=False,
                       clock=utc_now, progress=print):
    feed.require(stage in {"trial", "complete"}, "retrospective_stage")
    source, root, official, master, run = prepare_run(source, official_directory, expected_sha, output, resume=resume)
    with run_lock(root):
        if stage == "complete":
            feed.require((root / "trial").is_dir(), "retrospective_trial_required")
            read_bundle(root / "trial", {"matches.csv", "results.json", "summary.json", "report.md"})
        days = run["trial_dates"] if stage == "trial" else run["dates"]
        artifact = special = completed = None
        all_rows, day_hashes = [], {}
        for day in days:
            selected = official.schedule.loc[official.schedule.match_date.eq(day) & official.schedule.status.eq("completed")].sort_values("fixture_key")
            targets = selected.loc[:, list(champion.TARGET_COLUMNS)]
            destination = root / "days" / day
            if destination.exists():
                bodies = read_bundle(destination, {"predictions.json", "lineage.json"})
                rows = json.loads(bodies["predictions.json"])
                lineage = json.loads(bodies["lineage.json"])
                feed.require(lineage["same_day_results_used"] == lineage["future_results_used"] == 0
                             and (lineage["history_max_date"] is None or lineage["history_max_date"] < day),
                             "retrospective_resumed_cutoff")
                resumed = True
            else:
                unresolved = official.schedule.loc[official.schedule.match_date.lt(day) & ~official.schedule.status.eq("completed")]
                feed.require(unresolved.empty, "retrospective_history_incomplete")
                if artifact is None:
                    artifact, special, completed = load_state(source, official, master)
                rows, lineage = reconstruct_day(artifact, special, completed, master, targets, day, clock=clock)
                for row in rows:
                    row.update(run_id=run["run_id"], official_revision=run["revision"])
                validate_day(rows, targets, run, day)
                publish_bundle(root / "days", day, {"predictions.json": encoded(rows), "lineage.json": encoded(lineage)})
                resumed = False
            validate_day(rows, targets, run, day)
            all_rows.extend(rows)
            day_hashes[day] = digest((destination / "manifest.json").read_bytes())
            progress(json.dumps(dict(date=day, matches=len(rows), resumed=resumed, status="PREDICTIONS_SEALED")))
        seal = dict(run_id=run["run_id"], prediction_type=PREDICTION_TYPE, stage=stage,
                    days=day_hashes, predictions=len(all_rows))
        seal_path = root / "prediction-seals" / f"{stage}.json"
        if seal_path.exists():
            feed.require(json.loads(seal_path.read_bytes()) == seal, "retrospective_seal_changed")
        else:
            write_new(seal_path, encoded(seal))
        seal_hash = digest(seal_path.read_bytes())
        destination = root / stage
        if destination.exists():
            bodies = read_bundle(destination, {"matches.csv", "results.json", "summary.json", "report.md"})
            summary = json.loads(bodies["summary.json"])
            feed.require(summary["run_id"] == run["run_id"] and summary["prediction_seal_sha256"] == seal_hash,
                         "retrospective_evaluation_changed")
            return summary
        # No scores/outcomes enter the prediction phase above. Join only after its seal is durable.
        scored = score_predictions(all_rows, official, master)
        summary, report = evaluation_report(scored, run, stage, seal_hash, clock)
        publish_bundle(root, stage, {"matches.csv": csv_body(scored), "results.json": encoded(scored),
            "summary.json": encoded(summary), "report.md": report})
        feed.require(source_pins(source) == run["source_sha256"], "retrospective_inputs_changed")
        return summary


def compare_saved_predictions(root, saved_runtime):
    """Compare only native saved Champion rows after the independent run is sealed."""
    from scripts.update_champion_dashboard import saved_batches
    from src.features.elo_history import _prepare_ongoing_matches
    root, runtime = no_links(root), no_links(saved_runtime)
    run = json.loads((root / "run.json").read_bytes())
    bodies = read_bundle(root / "complete", {"matches.csv", "results.json", "summary.json", "report.md"})
    reconstructed = {r["fixture_key"]: r for r in json.loads(bodies["results.json"])}
    records, bindings = saved_batches(runtime)
    saved_identity = digest(encoded(dict(records=records, bindings=bindings)))
    destination = root / "live-comparison"
    if destination.exists():
        data = json.loads(read_bundle(destination, {"comparison.json", "comparison.csv"})["comparison.json"])
        feed.require(data["saved_batches_sha256"] == saved_identity and data["run_id"] == run["run_id"],
                     "retrospective_saved_comparison_changed")
        return data
    source = Path(run["source_root"])
    feed.require(source_pins(source) == run["source_sha256"], "retrospective_comparison_inputs")
    master = load_team_master(source / feed.TEAM_MASTER_PATH)
    current = feed.read_official_revision(root / "inputs" / run["revision"], master, expected_sha=run["manifest_sha256"])
    artifact = special = None
    comparisons = []
    for saved in records:
        if saved["match_date"] != "2026-10-09":
            continue
        key = saved["fixture_key"]
        feed.require(key in reconstructed, "retrospective_saved_fixture_missing")
        rebuilt = reconstructed[key]
        differences = {side: rebuilt[f"p_{side}"]-float(saved[f"a_p_{side}"])
                       for side in ("home", "draw", "away")}
        maximum = max(abs(v) for v in differences.values())
        item = dict(fixture_key=key, match_date=saved["match_date"], saved_generated_at=saved["prediction_generated_at"],
            reconstruction_calculated_at=rebuilt["calculated_at_utc"], saved_source_revision=saved["source_revision"],
            reconstructed_source_revision=run["revision"], exact_probability_match=all(v == 0 for v in differences.values()),
            match_within_1e_12=maximum <= 1e-12, maximum_absolute_probability_difference=maximum,
            **{f"delta_{side}": value for side, value in differences.items()},
            reason="MATCH_WITHIN_1E_12" if maximum <= 1e-12 else "UNRESOLVED_DIFFERENCE")
        if maximum > 1e-12:
            prior = feed.read_official_revision(feed.rooted(runtime / "official", "revisions/"+saved["source_revision"]), master)
            if artifact is None:
                artifact, special, _ = load_state(source, current, master)
            prior_history = _prepare_ongoing_matches(prior.completed, master, prior.observed_at)
            prior_history["match_date"] = prior_history.match_date.dt.strftime("%Y-%m-%d")
            prior_history = prior_history.loc[prior_history.match_date.lt(saved["match_date"]), list(HISTORY_COLUMNS)]
            selected = current.schedule.loc[current.schedule.fixture_key.eq(key), list(champion.TARGET_COLUMNS)]
            ratings = champion.replay_ratings(artifact.training, special, prior_history, master, saved["match_date"])
            check = champion.probability_rows(artifact, selected, ratings)[0]
            old_matches = all(abs(float(check[i])-float(saved[f"a_p_{side}"])) <= 1e-12
                              for i, side in enumerate(("away", "draw", "home")))
            def prior_results(official):
                return {r.fixture_key: (r.match_date, r.result) for r in official.completed.itertuples()
                        if r.match_date < saved["match_date"]}
            left, right = prior_results(prior), prior_results(current)
            changed = sorted(k for k in left.keys() | right.keys() if left.get(k) != right.get(k))
            item.update(saved_source_replay_matches=old_matches, earlier_history_differences=changed)
            if old_matches and changed:
                item["reason"] = "CONFIRMED_HISTORY_CHANGED_SINCE_SAVED_SOURCE"
        comparisons.append(item)
    report = dict(run_id=run["run_id"], prediction_type=PREDICTION_TYPE, disclaimer=DISCLAIMER,
        saved_batches_sha256=saved_identity, saved_prediction_count=len(records), compared_date="2026-10-09",
        comparisons=comparisons, live_predictions_and_metrics_combined=False)
    with run_lock(root):
        # CSV diagnostics remain flat; detailed history differences stay in JSON.
        columns = [dict((k, v) for k, v in row.items() if k != "earlier_history_differences") for row in comparisons]
        if columns:
            keys = list(dict.fromkeys(k for row in columns for k in row))
            columns = [{key: row.get(key) for key in keys} for row in columns]
        publish_bundle(root, "live-comparison", {"comparison.json": encoded(report), "comparison.csv": csv_body(columns)})
    return report
