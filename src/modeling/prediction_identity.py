"""Offline fixture bindings for immutable prospective prediction rows.

The prediction CSVs deliberately keep their historical ``match_id`` keys.
This module supplies the append-only fixture-key sidecar needed when the
official operational ID later moves between namespaces.
"""

from __future__ import annotations

from contextlib import contextmanager
import csv
import hashlib
import io
import json
import os
from pathlib import Path
import re
from typing import Callable, Mapping, Sequence
import uuid

import pandas as pd

from src.collect.teams import load_team_master


MATCH_PAGE_NAMESPACE = "jleague_match_page"
DATA_SITE_NAMESPACE = "jleague_data_site"
BINDING_COLUMNS = (
    "prediction_artifact", "prediction_match_id", "model_version", "fixture_key",
    "prediction_id_namespace", "identity_witness_revision_id",
    "identity_witness_manifest_sha256", "match_date", "home_team_id",
    "away_team_id", "prediction_generated_at",
)
DEFAULT_BINDING_PATH = Path("data/processed/predictions/2026_27_prediction_fixture_bindings.csv")
FROZEN_WITNESS_REVISION = "2758a644ff46888993f79fa44987079b187196e0ed204fb863ea645ff647dd3c"
FROZEN_WITNESS_MANIFEST_SHA256 = "c7bfa3b9bd113c1c34e016625a23935ce6bb712de4cdcc9b47bd5187fce044c2"
FROZEN_PREDICTIONS = {
    "data/processed/predictions/xg_challenger_prospective.csv": (
        "32fedd4f6b71d8f83e3275feb56653ff80b24a11514c7fd3df1854f58679d6aa", 2
    ),
    "data/processed/predictions/model_architecture_prospective.csv": (
        "e47d8a5df136939d3d629c4c0826e23c382786b3d99856987a3964b5842854ec", 4
    ),
}
FROZEN_PREDICTION_COLUMNS = {
    "data/processed/predictions/xg_challenger_prospective.csv": (
        "match_id", "match_date", "kickoff", "home_team_id", "away_team_id",
        "home_team_name", "away_team_name", "prediction_generated_at",
        "prospective_boundary", "model_version", "artifact_hash",
        "xg_pair_available", "xg_history_count_home", "xg_history_count_away",
        "elo_diff", "home_last5_xg_for", "home_last5_xg_against",
        "away_last5_xg_for", "away_last5_xg_against", "x0_p_away", "x0_p_draw",
        "x0_p_home", "x1_raw_p_away", "x1_raw_p_draw", "x1_raw_p_home",
        "operational_p_away", "operational_p_draw", "operational_p_home",
        "prediction_source", "predicted_class",
    ),
    "data/processed/predictions/model_architecture_prospective.csv": (
        "match_id", "match_date", "kickoff", "home_team_id", "away_team_id",
        "prediction_generated_at", "prospective_boundary", "model_version",
        "training_cutoff", "history_cutoff_exclusive", "artifact_hash", "p_away",
        "p_draw", "p_home", "predicted_class",
    ),
}
FROZEN_FIXTURES = {
    "100903": ("j1_2026_2027:kashima:gosaka", "2026-10-09", "team_0008", "team_0005"),
    "100901": ("j1_2026_2027:kashiwa:kobe", "2026-10-09", "team_0009", "team_0011"),
}


class PredictionIdentityError(ValueError):
    """A prediction binding, cardinality, or immutable append gate failed."""


def _sha(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()


def _csv(frame: pd.DataFrame) -> bytes:
    return frame.to_csv(index=False, lineterminator="\n").encode("utf-8")


def _suffix_bytes(frame: pd.DataFrame, *, header: bool) -> bytes:
    return frame.to_csv(index=False, header=header, lineterminator="\n").encode("utf-8")


def _append_suffix(path: Path, frame: pd.DataFrame) -> None:
    exists = path.exists()
    body = _suffix_bytes(frame, header=not exists)
    with path.open("ab" if exists else "xb") as target:
        target.write(body)
        target.flush()
        os.fsync(target.fileno())


def validate_prediction_bindings(frame: pd.DataFrame) -> pd.DataFrame:
    """Validate the exact frozen sidecar schema and both uniqueness keys."""
    if not isinstance(frame, pd.DataFrame) or tuple(frame.columns) != BINDING_COLUMNS:
        raise PredictionIdentityError("Prediction binding schema mismatch")
    if frame.isna().any().any() or frame.astype(str).apply(lambda col: col.str.strip().eq("")).any().any():
        raise PredictionIdentityError("Prediction binding contains a blank value")
    if not frame["prediction_id_namespace"].isin(
        [MATCH_PAGE_NAMESPACE, DATA_SITE_NAMESPACE]
    ).all():
        raise PredictionIdentityError("Prediction binding namespace is invalid")
    if frame.duplicated(["prediction_artifact", "prediction_match_id", "model_version"]).any():
        raise PredictionIdentityError("Duplicate prediction binding primary key")
    if frame.duplicated(["prediction_artifact", "fixture_key", "model_version"]).any():
        raise PredictionIdentityError("Duplicate prediction binding fixture key")
    return frame


def read_prediction_bindings(path: str | Path = DEFAULT_BINDING_PATH) -> pd.DataFrame:
    source = Path(path)
    if not source.is_file():
        raise PredictionIdentityError("Prediction binding sidecar is missing")
    try:
        frame = pd.read_csv(source, dtype=str, keep_default_na=False, encoding="utf-8-sig")
    except (OSError, ValueError, pd.errors.ParserError) as exc:
        raise PredictionIdentityError("Prediction binding sidecar is malformed") from exc
    return validate_prediction_bindings(frame)


def validate_complete_sidecar(
    *, repository_root: str | Path, binding_path: str | Path = DEFAULT_BINDING_PATH,
    prediction_artifacts: Sequence[str] = tuple(FROZEN_PREDICTIONS),
) -> pd.DataFrame:
    """Require one exact binding for every immutable prediction row."""
    root = Path(repository_root)
    bindings = read_prediction_bindings(binding_path)
    if set(bindings["prediction_artifact"]) != set(prediction_artifacts):
        raise PredictionIdentityError("Prediction binding artifact set is incomplete or extra")
    for artifact in prediction_artifacts:
        path = root / Path(artifact)
        if not path.is_file():
            raise PredictionIdentityError(f"Prediction artifact is missing: {artifact}")
        predictions = pd.read_csv(path, dtype=str, keep_default_na=False, encoding="utf-8-sig")
        if not {"match_id", "model_version", "match_date", "home_team_id", "away_team_id", "prediction_generated_at"} <= set(predictions.columns):
            raise PredictionIdentityError(f"Prediction artifact schema mismatch: {artifact}")
        expected_columns = FROZEN_PREDICTION_COLUMNS.get(artifact)
        if expected_columns is not None and tuple(predictions.columns) != expected_columns:
            raise PredictionIdentityError(f"Prediction artifact schema mismatch: {artifact}")
        selected = bindings.loc[bindings.prediction_artifact.eq(artifact)]
        merged = predictions.merge(
            selected,
            left_on=["match_id", "model_version"],
            right_on=["prediction_match_id", "model_version"],
            how="left", validate="one_to_one", suffixes=("_prediction", "_binding"),
        )
        if len(merged) != len(predictions) or merged["fixture_key"].isna().any():
            raise PredictionIdentityError(f"Prediction binding coverage is incomplete: {artifact}")
        if (
            merged["match_date_prediction"].ne(merged["match_date_binding"]).any()
            or merged["home_team_id_prediction"].ne(merged["home_team_id_binding"]).any()
            or merged["away_team_id_prediction"].ne(merged["away_team_id_binding"]).any()
            or merged["prediction_generated_at_prediction"].ne(merged["prediction_generated_at_binding"]).any()
        ):
            raise PredictionIdentityError(f"Prediction binding identity mismatch: {artifact}")
        if len(selected) != len(predictions):
            raise PredictionIdentityError(f"Prediction binding contains orphan rows: {artifact}")
    return bindings


def build_frozen_prediction_bindings(
    *,
    repository_root: str | Path,
    witness_revision_dir: str | Path,
    output_path: str | Path = DEFAULT_BINDING_PATH,
    expected_predictions: Mapping[str, tuple[str, int]] = FROZEN_PREDICTIONS,
    witness_revision_id: str = FROZEN_WITNESS_REVISION,
    witness_manifest_sha256: str = FROZEN_WITNESS_MANIFEST_SHA256,
    expected_fixtures: Mapping[str, tuple[str, str, str, str]] = FROZEN_FIXTURES,
) -> pd.DataFrame:
    """Exclusively create the frozen six-row sidecar from offline artifacts."""
    root, revision, output = Path(repository_root), Path(witness_revision_dir), Path(output_path)
    if output.exists():
        raise PredictionIdentityError("Prediction binding sidecar already exists")
    manifest_bytes = (revision / "manifest.json").read_bytes()
    manifest = json.loads(manifest_bytes)
    if (
        revision.name != witness_revision_id
        or _sha(manifest_bytes) != witness_manifest_sha256
        or manifest.get("summary", {}).get("publication_status") != "published"
    ):
        raise PredictionIdentityError("Identity witness revision mismatch")
    files = manifest.get("files")
    if not isinstance(files, dict) or "observations.json" not in files:
        raise PredictionIdentityError("Identity witness file manifest is incomplete")
    for name, digest in files.items():
        path = revision / name
        if not path.is_file() or _sha(path.read_bytes()) != digest:
            raise PredictionIdentityError("Identity witness artifact hash mismatch")
    observations = json.loads((revision / "observations.json").read_bytes())
    by_page = {}
    master = load_team_master()
    for row in observations:
        match_id = row.get("match_id")
        if match_id:
            if match_id in by_page:
                raise PredictionIdentityError("Identity witness has ambiguous match_id")
            page_url = row.get("evidence_url") or ""
            page_match = re.fullmatch(
                r"https://www\.jleague\.jp/match/j1/(2026|2027)/([0-9]{6})/",
                page_url,
            )
            if row.get("status") != "scheduled" or page_match is None or page_match[2] != match_id:
                continue
            by_page[match_id] = row
    bindings = []
    for artifact, (digest, expected_rows) in expected_predictions.items():
        path = root / Path(artifact)
        body = path.read_bytes()
        if _sha(body) != digest:
            raise PredictionIdentityError(f"Frozen prediction hash mismatch: {artifact}")
        predictions = pd.read_csv(path, dtype=str, keep_default_na=False, encoding="utf-8-sig")
        required = {
            "match_id", "match_date", "home_team_id", "away_team_id",
            "model_version", "prediction_generated_at",
        }
        expected_columns = FROZEN_PREDICTION_COLUMNS.get(artifact)
        if (
            len(predictions) != expected_rows or not required <= set(predictions.columns)
            or (expected_columns is not None and tuple(predictions.columns) != expected_columns)
        ):
            raise PredictionIdentityError(f"Frozen prediction schema/row mismatch: {artifact}")
        if predictions.duplicated(["match_id", "model_version"]).any():
            raise PredictionIdentityError(f"Frozen prediction keys are ambiguous: {artifact}")
        for prediction in predictions.itertuples(index=False):
            key = str(prediction.match_id)
            frozen = expected_fixtures.get(key)
            observed = by_page.get(key)
            if frozen is None or observed is None:
                raise PredictionIdentityError("Prediction does not resolve one-to-one in witness")
            fixture_key, match_date, home_id, away_id = frozen
            try:
                observed_home = master.resolve_team_id(
                    observed["home_team"], source="jleague_data_site", on=observed["match_date"]
                )
                observed_away = master.resolve_team_id(
                    observed["away_team"], source="jleague_data_site", on=observed["match_date"]
                )
            except Exception as exc:
                raise PredictionIdentityError("Witness team identity resolution failed") from exc
            if (
                observed.get("fixture_key") != fixture_key
                or observed.get("match_date") != match_date
                or observed_home != home_id or observed_away != away_id
                or str(prediction.match_date) != match_date
                or str(prediction.home_team_id) != home_id
                or str(prediction.away_team_id) != away_id
            ):
                raise PredictionIdentityError("Prediction/witness fixture identity mismatch")
            bindings.append({
                "prediction_artifact": artifact,
                "prediction_match_id": key,
                "model_version": str(prediction.model_version),
                "fixture_key": fixture_key,
                "prediction_id_namespace": MATCH_PAGE_NAMESPACE,
                "identity_witness_revision_id": witness_revision_id,
                "identity_witness_manifest_sha256": witness_manifest_sha256,
                "match_date": match_date,
                "home_team_id": home_id,
                "away_team_id": away_id,
                "prediction_generated_at": str(prediction.prediction_generated_at),
            })
    frame = validate_prediction_bindings(pd.DataFrame(bindings, columns=BINDING_COLUMNS))
    if len(frame) != sum(rows for _digest, rows in expected_predictions.values()):
        raise PredictionIdentityError("Frozen prediction binding input is partial or extra")
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("xb") as target:
        target.write(_csv(frame))
        target.flush()
        os.fsync(target.fileno())
    return frame


def fixture_duplicates(
    records: pd.DataFrame,
    bindings: pd.DataFrame,
    *,
    prediction_artifact: str,
    fixture_keys: Sequence[str],
) -> pd.Series:
    """Return records already bound by artifact/fixture/model, independent of ID."""
    validate_prediction_bindings(bindings)
    if len(records) != len(fixture_keys):
        raise PredictionIdentityError("Prediction/binding fixture cardinality mismatch")
    existing = set(zip(
        bindings.loc[bindings.prediction_artifact.eq(prediction_artifact), "fixture_key"],
        bindings.loc[bindings.prediction_artifact.eq(prediction_artifact), "model_version"],
    ))
    return pd.Series([
        (str(fixture), str(version)) in existing
        for fixture, version in zip(fixture_keys, records["model_version"])
    ], index=records.index)


def make_binding_rows(
    records: pd.DataFrame,
    targets: pd.DataFrame,
    *,
    prediction_artifact: str,
    identity_witness_revision_id: str,
    identity_witness_manifest_sha256: str,
) -> pd.DataFrame:
    """Build exact sidecar rows for one already-resolved future target batch."""
    required = {"fixture_key", "match_id", "match_id_namespace", "match_date"}
    if len(records) != len(targets) or required - set(targets.columns):
        raise PredictionIdentityError("Prediction target identity schema/cardinality mismatch")
    target_by_id = targets.set_index("match_id", verify_integrity=True)
    rows = []
    for record in records.itertuples(index=False):
        try:
            target = target_by_id.loc[str(record.match_id)]
        except KeyError as exc:
            raise PredictionIdentityError("Prediction does not resolve to its target fixture") from exc
        if target.match_id_namespace not in {MATCH_PAGE_NAMESPACE, DATA_SITE_NAMESPACE}:
            raise PredictionIdentityError("Target operational namespace is invalid")
        rows.append({
            "prediction_artifact": prediction_artifact,
            "prediction_match_id": str(record.match_id),
            "model_version": str(record.model_version),
            "fixture_key": str(target.fixture_key),
            "prediction_id_namespace": str(target.match_id_namespace),
            "identity_witness_revision_id": identity_witness_revision_id,
            "identity_witness_manifest_sha256": identity_witness_manifest_sha256,
            "match_date": str(record.match_date),
            "home_team_id": str(record.home_team_id),
            "away_team_id": str(record.away_team_id),
            "prediction_generated_at": str(record.prediction_generated_at),
        })
    return validate_prediction_bindings(pd.DataFrame(rows, columns=BINDING_COLUMNS))


def append_prediction_and_bindings(
    records: pd.DataFrame,
    binding_rows: pd.DataFrame,
    *,
    prediction_path: str | Path,
    binding_path: str | Path = DEFAULT_BINDING_PATH,
    prediction_columns: Sequence[str],
    prediction_validator: Callable[[pd.DataFrame], None],
) -> tuple[int, int]:
    """Append prediction and binding suffixes as one recoverable local operation."""
    output, sidecar = Path(prediction_path), Path(binding_path)
    journal = sidecar.with_name(f".{sidecar.name}.journal.json")
    lock = sidecar.with_name(f".{sidecar.name}.lock")
    if journal.exists():
        if lock.exists():
            raise PredictionIdentityError("Prediction binding writer lock exists during recovery")
        recover_prediction_append(
            prediction_path=output, binding_path=sidecar,
            prediction_columns=prediction_columns,
            prediction_validator=prediction_validator,
        )
    prediction_validator(records)
    validate_prediction_bindings(binding_rows)
    if len(records) != len(binding_rows):
        raise PredictionIdentityError("Prediction/binding append cardinality mismatch")
    expected_pairs = set(zip(records["match_id"].astype(str), records["model_version"].astype(str)))
    actual_pairs = set(zip(binding_rows["prediction_match_id"], binding_rows["model_version"]))
    if expected_pairs != actual_pairs:
        raise PredictionIdentityError("Prediction/binding append keys mismatch")
    existing_predictions = (
        pd.read_csv(output, dtype=str, keep_default_na=False, encoding="utf-8-sig")
        if output.exists() else pd.DataFrame(columns=prediction_columns)
    )
    if not existing_predictions.empty or output.exists():
        prediction_validator(existing_predictions)
    existing_bindings = (
        read_prediction_bindings(sidecar)
        if sidecar.exists() else pd.DataFrame(columns=BINDING_COLUMNS)
    )
    prediction_keys = set(zip(existing_predictions["match_id"], existing_predictions["model_version"]))
    binding_keys = set(zip(
        existing_bindings["prediction_artifact"], existing_bindings["prediction_match_id"],
        existing_bindings["model_version"],
    ))
    fixture_keys = set(zip(
        existing_bindings["prediction_artifact"], existing_bindings["fixture_key"],
        existing_bindings["model_version"],
    ))
    new_record_rows, new_binding_rows, duplicates = [], [], 0
    for (_, record), (_, binding) in zip(records.iterrows(), binding_rows.iterrows()):
        pkey = (str(record.match_id), str(record.model_version))
        bkey = (binding.prediction_artifact, binding.prediction_match_id, binding.model_version)
        fkey = (binding.prediction_artifact, binding.fixture_key, binding.model_version)
        present = (pkey in prediction_keys, bkey in binding_keys)
        if present == (True, True):
            existing_binding = existing_bindings.loc[
                existing_bindings.prediction_artifact.eq(binding.prediction_artifact)
                & existing_bindings.prediction_match_id.eq(binding.prediction_match_id)
                & existing_bindings.model_version.eq(binding.model_version)
            ].iloc[0]
            if any(str(existing_binding[column]) != str(binding[column]) for column in BINDING_COLUMNS):
                raise PredictionIdentityError("Existing prediction binding conflicts with append journal")
            duplicates += 1
            continue
        if fkey in fixture_keys and present == (False, False):
            duplicates += 1
            continue
        if present != (False, False):
            raise PredictionIdentityError("Prediction/binding append is incomplete")
        new_record_rows.append(record.to_dict())
        new_binding_rows.append(binding.to_dict())
    if not new_record_rows:
        return 0, duplicates
    new_predictions = pd.DataFrame(new_record_rows, columns=prediction_columns)
    new_bindings = validate_prediction_bindings(pd.DataFrame(new_binding_rows, columns=BINDING_COLUMNS))
    combined_predictions = pd.concat([existing_predictions, new_predictions], ignore_index=True)
    combined_bindings = validate_prediction_bindings(
        pd.concat([existing_bindings, new_bindings], ignore_index=True)
    )
    prediction_validator(combined_predictions)
    output.parent.mkdir(parents=True, exist_ok=True)
    sidecar.parent.mkdir(parents=True, exist_ok=True)
    try:
        lock_handle = lock.open("x", encoding="utf-8")
    except FileExistsError as exc:
        raise PredictionIdentityError("Prediction binding writer lock exists") from exc
    old_prediction = output.read_bytes() if output.exists() else None
    old_binding = sidecar.read_bytes() if sidecar.exists() else None
    try:
        with lock_handle:
            lock_handle.write(str(os.getpid()))
        journal.write_text(json.dumps({
            "prediction_sha256": _sha(
                (old_prediction or b"") + _suffix_bytes(new_predictions, header=old_prediction is None)
            ),
            "binding_sha256": _sha(
                (old_binding or b"") + _suffix_bytes(new_bindings, header=old_binding is None)
            ),
            "prediction_rows": json.loads(new_predictions.to_json(orient="records")),
            "binding_rows": json.loads(new_bindings.to_json(orient="records")),
        }, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
        _append_suffix(output, new_predictions)
        _append_suffix(sidecar, new_bindings)
        frozen = json.loads(journal.read_bytes())
        if (
            _sha(output.read_bytes()) != frozen["prediction_sha256"]
            or _sha(sidecar.read_bytes()) != frozen["binding_sha256"]
        ):
            raise PredictionIdentityError("Prediction append hash verification failed")
        journal.unlink()
    except BaseException:
        for path, body in ((output, old_prediction), (sidecar, old_binding)):
            if body is None:
                path.unlink(missing_ok=True)
            else:
                temporary = path.with_name(f".{path.name}-restore-{uuid.uuid4().hex}.tmp")
                temporary.write_bytes(body)
                os.replace(temporary, path)
        journal.unlink(missing_ok=True)
        raise
    finally:
        lock.unlink(missing_ok=True)
    return len(new_predictions), duplicates


def recover_prediction_append(
    *,
    prediction_path: str | Path,
    binding_path: str | Path,
    prediction_columns: Sequence[str],
    prediction_validator: Callable[[pd.DataFrame], None],
) -> tuple[int, int]:
    """Finish only missing exact journal suffixes after an interrupted append."""
    output, sidecar = Path(prediction_path), Path(binding_path)
    journal = sidecar.with_name(f".{sidecar.name}.journal.json")
    if not journal.is_file():
        raise PredictionIdentityError("Prediction append journal is missing")
    try:
        frozen = json.loads(journal.read_bytes())
        desired_predictions = pd.DataFrame(frozen["prediction_rows"], columns=prediction_columns)
        desired_bindings = validate_prediction_bindings(
            pd.DataFrame(frozen["binding_rows"], columns=BINDING_COLUMNS)
        )
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise PredictionIdentityError("Prediction append journal is malformed") from exc
    prediction_validator(desired_predictions)
    existing_predictions = (
        pd.read_csv(output, dtype=str, keep_default_na=False, encoding="utf-8-sig")
        if output.exists() else pd.DataFrame(columns=prediction_columns)
    )
    existing_bindings = (
        read_prediction_bindings(sidecar)
        if sidecar.exists() else pd.DataFrame(columns=BINDING_COLUMNS)
    )
    if output.exists():
        prediction_validator(existing_predictions)
    prediction_additions = []
    for row in desired_predictions.to_dict("records"):
        found = existing_predictions.loc[
            existing_predictions["match_id"].astype(str).eq(str(row["match_id"]))
            & existing_predictions["model_version"].astype(str).eq(str(row["model_version"]))
        ]
        if found.empty:
            prediction_additions.append(row)
        elif len(found) != 1 or any(str(found.iloc[0][column]) != str(row[column]) for column in prediction_columns):
            raise PredictionIdentityError("Prediction journal conflicts with an existing row")
    binding_additions = []
    for row in desired_bindings.to_dict("records"):
        found = existing_bindings.loc[
            existing_bindings["prediction_artifact"].eq(row["prediction_artifact"])
            & existing_bindings["prediction_match_id"].eq(row["prediction_match_id"])
            & existing_bindings["model_version"].eq(row["model_version"])
        ]
        fixture_found = existing_bindings.loc[
            existing_bindings["prediction_artifact"].eq(row["prediction_artifact"])
            & existing_bindings["fixture_key"].eq(row["fixture_key"])
            & existing_bindings["model_version"].eq(row["model_version"])
        ]
        if found.empty and fixture_found.empty:
            binding_additions.append(row)
        elif len(found) != 1 or any(str(found.iloc[0][column]) != str(row[column]) for column in BINDING_COLUMNS):
            raise PredictionIdentityError("Binding journal conflicts with an existing row")
    # Recovery is deliberately suffix-only. The journal remains until both
    # suffixes validate, so another recovery cannot append either row twice.
    if prediction_additions:
        pd.DataFrame(prediction_additions, columns=prediction_columns).to_csv(
            output, mode="a" if output.exists() else "x", header=not output.exists(),
            index=False, lineterminator="\n",
        )
    if binding_additions:
        pd.DataFrame(binding_additions, columns=BINDING_COLUMNS).to_csv(
            sidecar, mode="a" if sidecar.exists() else "x", header=not sidecar.exists(),
            index=False, lineterminator="\n",
        )
    prediction_validator(pd.read_csv(output, dtype=str, keep_default_na=False))
    validate_prediction_bindings(pd.read_csv(sidecar, dtype=str, keep_default_na=False))
    if (
        _sha(output.read_bytes()) != frozen.get("prediction_sha256")
        or _sha(sidecar.read_bytes()) != frozen.get("binding_sha256")
    ):
        raise PredictionIdentityError("Recovered prediction append hash mismatch")
    journal.unlink()
    return len(prediction_additions), len(binding_additions)


def resolve_predictions_to_completed(
    predictions: pd.DataFrame,
    bindings: pd.DataFrame,
    bridges: pd.DataFrame,
    completed: pd.DataFrame,
    *,
    prediction_artifact: str,
) -> pd.DataFrame:
    """Resolve immutable prediction IDs to outcomes only through fixture bridges."""
    validate_prediction_bindings(bindings)
    bound = bindings.loc[bindings.prediction_artifact.eq(prediction_artifact)]
    merged = predictions.merge(
        bound, left_on=["match_id", "model_version"],
        right_on=["prediction_match_id", "model_version"], how="left", validate="one_to_one",
        suffixes=("_prediction", "_binding"),
    )
    if merged["fixture_key"].isna().any():
        raise PredictionIdentityError("Prediction has no fixture binding")
    if (
        merged["match_date_prediction"].astype(str).ne(merged["match_date_binding"]).any()
        or merged["home_team_id_prediction"].ne(merged["home_team_id_binding"]).any()
        or merged["away_team_id_prediction"].ne(merged["away_team_id_binding"]).any()
    ):
        raise PredictionIdentityError("Prediction/binding fixture identity mismatch")
    if bridges.duplicated("fixture_key").any() or bridges.duplicated("data_site_match_id").any():
        raise PredictionIdentityError("Identity bridge is ambiguous")
    merged = merged.merge(
        bridges[["fixture_key", "competition_key", "data_site_match_id"]],
        on="fixture_key", how="left", validate="many_to_one",
    )
    if merged["data_site_match_id"].isna().any():
        raise PredictionIdentityError("Prediction fixture has no accepted identity bridge")
    renamed = completed.rename(columns={
        "match_id": "completed_match_id", "match_date": "match_date_outcome",
        "home_team_id": "home_team_id_outcome", "away_team_id": "away_team_id_outcome",
        "competition_key": "competition_key_outcome",
    })
    outcome = merged.merge(
        renamed, left_on="data_site_match_id", right_on="completed_match_id",
        how="left", validate="many_to_one",
    )
    required = ["result", "match_date_outcome", "home_team_id_outcome", "away_team_id_outcome"]
    if any(column not in outcome or outcome[column].isna().any() for column in required):
        raise PredictionIdentityError("Completed outcome join is missing or malformed")
    if (
        outcome["match_date_prediction"].astype(str).ne(outcome["match_date_outcome"].astype(str)).any()
        or outcome["home_team_id_prediction"].ne(outcome["home_team_id_outcome"]).any()
        or outcome["away_team_id_prediction"].ne(outcome["away_team_id_outcome"]).any()
        or (
            "competition_key_outcome" in outcome
            and outcome["competition_key"].ne(outcome["competition_key_outcome"]).any()
        )
    ):
        raise PredictionIdentityError("Prediction/outcome fixture identity mismatch")
    return outcome
