"""Frozen one-shot evaluator for the Team Draw Propensity family.

The default CLI runs only the read-only preflight through the fresh all-row
``A_Y`` reference gate.  The matched DP0/DP1 evaluation is reachable only
through the separately confirmed formal path.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from src.features.draw_propensity import (
    MODEL_CANDIDATES,
    OUTPUT_COLUMNS,
    load_j1_matches,
)
from src.modeling.player_workload_evaluation import (
    CLASS_ORDER,
    _add_elo,
    _align_predictions,
    _metrics,
    _validate_probabilities,
)


ROOT = Path(__file__).resolve().parents[2]
MATCH_DIR = ROOT / "data/processed/jleague"
ARTIFACT_PATH = (
    ROOT / "data/processed/features/2015_2024_j1_draw_propensity_features.csv"
)
EVALUATION_DOC_PATH = ROOT / "docs/TEAM_DRAW_PROPENSITY_EVALUATION.md"
ARTIFACT_SHA256 = "97b33269a11b62f94dbd4b83924b97cc1cb1cb250ae0eb636ca5d8ccc6ba36a5"

FOLDS = (2020, 2021, 2022, 2023, 2024)
DP0_FEATURES = ("elo_diff",)
DP1_FEATURES = ("elo_diff", *MODEL_CANDIDATES)
MODEL_PARAMS = {"C": 1.0, "solver": "lbfgs", "max_iter": 1000, "random_state": 0}
TARGET_IDENTITY = ("match_id", "match_date", "season", "home_team_id", "away_team_id")
EXPECTED_FOLD_COUNTS = {
    2020: (1530, 1485, 306, 297),
    2021: (1836, 1782, 380, 370),
    2022: (2216, 2152, 306, 297),
    2023: (2522, 2449, 306, 297),
    2024: (2828, 2746, 380, 370),
}
EXPECTED_POOLED_ELIGIBLE = 1631
EXPECTED_POOLED_FULL = 1678
EXPECTED_A_Y_LL = {
    2020: 1.023119734659012,
    2021: 1.0253437210487792,
    2022: 1.0940186385371449,
    2023: 1.0604285568595655,
    2024: 1.079241181120235,
}
PREFLIGHT_STATUS = "PREFLIGHT_PASS"
EXISTING_BASELINE_PREDICTION_REUSED = False


class DrawPropensityEvaluationError(ValueError):
    """A frozen artifact, source, reference, or evaluation gate failed."""


@dataclass(frozen=True)
class PreflightResult:
    status: str
    artifact_sha256: str
    schema_identity_gate: str
    eligible_counts_gate: str
    fold_counts: dict[int, tuple[int, int, int, int]]
    pooled_eligible_validation: int
    pooled_full_validation: int
    a_y_gate: str
    a_y_log_loss: dict[int, float]


@dataclass(frozen=True)
class _PreflightContext:
    public: PreflightResult
    data: pd.DataFrame
    a_y: dict[int, dict]


def artifact_sha256(path: str | Path = ARTIFACT_PATH) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def assert_artifact_sha(path: str | Path = ARTIFACT_PATH) -> str:
    actual = artifact_sha256(path)
    if actual != ARTIFACT_SHA256:
        raise DrawPropensityEvaluationError(
            "BLOCKED_REFERENCE_MISMATCH: artifact SHA-256"
        )
    return actual


def _read_artifact(path: str | Path = ARTIFACT_PATH) -> pd.DataFrame:
    return pd.read_csv(
        path,
        dtype={
            "match_id": "string",
            "match_date": "string",
            "home_team_id": "string",
            "away_team_id": "string",
        },
        keep_default_na=True,
    )


def validate_artifact(targets: pd.DataFrame, artifact: pd.DataFrame) -> None:
    """Validate exact schema, cardinality, keyed identity, and candidates."""
    if tuple(artifact.columns) != OUTPUT_COLUMNS or len(artifact.columns) != 21:
        raise DrawPropensityEvaluationError("Draw propensity artifact schema mismatch")
    if len(artifact) != 3208 or artifact.match_id.nunique(dropna=False) != 3208:
        raise DrawPropensityEvaluationError("Artifact row/unique-ID mismatch")
    if len(targets) != 3208 or targets.match_id.nunique(dropna=False) != 3208:
        raise DrawPropensityEvaluationError("Target row/unique-ID mismatch")

    target_ids = set(targets.match_id.astype(str))
    artifact_ids = set(artifact.match_id.astype(str))
    if target_ids != artifact_ids:
        raise DrawPropensityEvaluationError("Target and artifact match-ID sets differ")

    left = targets.loc[:, list(TARGET_IDENTITY)].copy()
    right = artifact.loc[:, list(TARGET_IDENTITY)].copy()
    left["match_id"] = left.match_id.astype(str)
    right["match_id"] = right.match_id.astype(str)
    if not right.match_date.astype(str).str.fullmatch(
        r"[0-9]{4}-[0-9]{2}-[0-9]{2}"
    ).all():
        raise DrawPropensityEvaluationError("Artifact match_date is not ISO YYYY-MM-DD")
    left["match_date"] = pd.to_datetime(left.match_date, errors="raise")
    right["match_date"] = pd.to_datetime(right.match_date, errors="raise")
    joined = left.merge(
        right, on="match_id", suffixes=("_target", "_artifact"), validate="one_to_one"
    )
    for column in ("match_date", "season", "home_team_id", "away_team_id"):
        if not joined[f"{column}_target"].eq(joined[f"{column}_artifact"]).all():
            raise DrawPropensityEvaluationError(
                f"Target/artifact identity mismatch: {column}"
            )

    for column in MODEL_CANDIDATES:
        raw = artifact[column]
        try:
            numeric = pd.to_numeric(raw, errors="raise")
        except (TypeError, ValueError) as exc:
            raise DrawPropensityEvaluationError(
                f"Invalid non-null candidate: {column}"
            ) from exc
        non_null = numeric.notna()
        values = numeric.loc[non_null].to_numpy(dtype=float)
        if (
            not np.isfinite(values).all()
            or (values < 0).any()
            or (values > 1).any()
        ):
            raise DrawPropensityEvaluationError(
                f"Invalid non-null candidate: {column}"
            )


def add_primary_eligibility(artifact: pd.DataFrame) -> pd.DataFrame:
    """Mark complete valid rows without filling or transforming any null."""
    result = artifact.copy(deep=True)
    values = result.loc[:, list(MODEL_CANDIDATES)]
    result["primary_eligible"] = values.notna().all(axis=1)
    return result


def validate_fold_counts(data: pd.DataFrame) -> dict[int, tuple[int, int, int, int]]:
    observed = {}
    for year, expected in EXPECTED_FOLD_COUNTS.items():
        train = data.season.lt(year)
        validation = data.season.eq(year)
        counts = (
            int(train.sum()),
            int((train & data.primary_eligible).sum()),
            int(validation.sum()),
            int((validation & data.primary_eligible).sum()),
        )
        if counts != expected:
            raise DrawPropensityEvaluationError(
                f"Fold-count mismatch for {year}: {counts} != {expected}"
            )
        observed[year] = counts
    pooled_eligible = sum(counts[3] for counts in observed.values())
    pooled_full = sum(counts[2] for counts in observed.values())
    if pooled_eligible != EXPECTED_POOLED_ELIGIBLE:
        raise DrawPropensityEvaluationError(
            f"Pooled eligible validation mismatch: {pooled_eligible}"
        )
    if pooled_full != EXPECTED_POOLED_FULL:
        raise DrawPropensityEvaluationError(
            f"Pooled full validation mismatch: {pooled_full}"
        )
    return observed


def _fit(train: pd.DataFrame, validation: pd.DataFrame, features) -> np.ndarray:
    model = Pipeline(
        [
            ("scaler", StandardScaler()),
            ("logistic", LogisticRegression(**MODEL_PARAMS)),
        ]
    )
    model.fit(train.loc[:, features], train["result"])
    if not np.array_equal(model.named_steps["logistic"].classes_, CLASS_ORDER):
        raise DrawPropensityEvaluationError("Expected class order [0, 1, 2]")
    return _validate_probabilities(
        model.predict_proba(validation.loc[:, features])
    )


def _metric_dict(labels, probabilities) -> dict:
    return asdict(_metrics(labels, probabilities))


def _metric_delta(challenger: dict, baseline: dict) -> dict:
    return {
        name: challenger[name] - baseline[name]
        for name in ("accuracy", "log_loss", "brier")
    }


def assert_same_fold_inputs(
    dp0_train: pd.DataFrame,
    dp1_train: pd.DataFrame,
    dp0_validation: pd.DataFrame,
    dp1_validation: pd.DataFrame,
) -> None:
    for left, right, label in (
        (dp0_train, dp1_train, "training"),
        (dp0_validation, dp1_validation, "validation"),
    ):
        if left.match_id.astype(str).tolist() != right.match_id.astype(str).tolist():
            raise DrawPropensityEvaluationError(
                f"DP0/DP1 {label} match IDs differ"
            )
        if left.result.astype(int).tolist() != right.result.astype(int).tolist():
            raise DrawPropensityEvaluationError(f"DP0/DP1 {label} labels differ")


def assert_a_y_references(a_y: dict[int, dict]) -> None:
    for year in FOLDS:
        actual = a_y[year]["metrics"]["log_loss"]
        if not np.isclose(actual, EXPECTED_A_Y_LL[year], rtol=0, atol=1e-12):
            raise DrawPropensityEvaluationError(
                f"BLOCKED_REFERENCE_MISMATCH: A_Y {year} Log Loss"
            )


def _evaluate_a_y(data: pd.DataFrame) -> dict[int, dict]:
    result = {}
    for year in FOLDS:
        train = data.loc[data.season.lt(year)].copy()
        validation = data.loc[data.season.eq(year)].copy()
        probabilities = _fit(train, validation, DP0_FEATURES)
        labels = validation.result.to_numpy(dtype=int)
        result[year] = {
            "train_ids": train.match_id.astype(str).tolist(),
            "validation_ids": validation.match_id.astype(str).tolist(),
            "labels": labels,
            "probabilities": probabilities,
            "metrics": _metric_dict(labels, probabilities),
        }
    assert_a_y_references(result)
    return result


def _preflight_context(
    *,
    match_dir: str | Path = MATCH_DIR,
    artifact_path: str | Path = ARTIFACT_PATH,
) -> _PreflightContext:
    digest = assert_artifact_sha(artifact_path)
    targets = load_j1_matches(match_dir)
    artifact = _read_artifact(artifact_path)
    validate_artifact(targets, artifact)
    artifact = add_primary_eligibility(artifact)

    eligibility = artifact.loc[:, ["match_id", "season", "primary_eligible"]]
    fold_counts = validate_fold_counts(eligibility)

    # Elo is deliberately replayed over all 3,208 targets before eligibility
    # is joined or filtered.
    elo = _add_elo(targets)
    artifact_for_join = artifact.drop(
        columns=["match_date", "season", "home_team_id", "away_team_id"]
    )
    data = elo.merge(artifact_for_join, on="match_id", validate="one_to_one")
    a_y = _evaluate_a_y(data)
    public = PreflightResult(
        status=PREFLIGHT_STATUS,
        artifact_sha256=digest,
        schema_identity_gate="PASS",
        eligible_counts_gate="PASS",
        fold_counts=fold_counts,
        pooled_eligible_validation=EXPECTED_POOLED_ELIGIBLE,
        pooled_full_validation=EXPECTED_POOLED_FULL,
        a_y_gate="PASS",
        a_y_log_loss={year: a_y[year]["metrics"]["log_loss"] for year in FOLDS},
    )
    return _PreflightContext(public=public, data=data, a_y=a_y)


def preflight(**kwargs) -> PreflightResult:
    """Run through the fresh A_Y gate without fitting DP1 or writing a report."""
    return _preflight_context(**kwargs).public


def _operational_fallback(
    *,
    a_y_probabilities,
    a_y_ids,
    dp1_probabilities,
    dp1_ids,
    validation_ids,
    eligible_ids,
) -> np.ndarray:
    """Use DP1 on eligible IDs and fresh A_Y elsewhere, aligned by match_id."""
    target = pd.Index(pd.Series(validation_ids, dtype="string"))
    eligible = pd.Index(pd.Series(eligible_ids, dtype="string"))
    if not target.is_unique or not eligible.is_unique:
        raise DrawPropensityEvaluationError("Operational alignment IDs must be unique")
    if not set(eligible).issubset(set(target)):
        raise DrawPropensityEvaluationError("Eligible IDs are not a validation subset")
    output = _align_predictions(a_y_probabilities, a_y_ids, target).copy()
    challenger = _align_predictions(dp1_probabilities, dp1_ids, eligible)
    positions = target.get_indexer(eligible)
    if (positions < 0).any():
        raise DrawPropensityEvaluationError("Operational match-ID alignment failed")
    output[positions] = challenger
    return _validate_probabilities(output)


def _draw_diagnostic(labels, dp0_probabilities, dp1_probabilities) -> dict:
    labels = np.asarray(labels, dtype=int)
    dp0 = _validate_probabilities(dp0_probabilities)
    dp1 = _validate_probabilities(dp1_probabilities)
    return {
        "actual": np.bincount(labels, minlength=3).astype(int).tolist(),
        "dp0_argmax": np.bincount(
            np.asarray(CLASS_ORDER)[dp0.argmax(axis=1)], minlength=3
        ).astype(int).tolist(),
        "dp1_argmax": np.bincount(
            np.asarray(CLASS_ORDER)[dp1.argmax(axis=1)], minlength=3
        ).astype(int).tolist(),
        "dp0_mean_draw_probability": float(dp0[:, 1].mean()),
        "dp1_mean_draw_probability": float(dp1[:, 1].mean()),
        "delta_mean_draw_probability": float(dp1[:, 1].mean() - dp0[:, 1].mean()),
    }


def frozen_decision(folds: dict, pooled: dict) -> str:
    improved = sum(
        folds[year]["dp1"]["log_loss"] < folds[year]["dp0"]["log_loss"]
        for year in FOLDS
    )
    if (
        pooled["dp1"]["log_loss"] < pooled["dp0"]["log_loss"]
        and pooled["dp1"]["brier"] < pooled["dp0"]["brier"]
        and improved >= 3
    ):
        return "CONTINUE_DRAW_PROPENSITY_LANE"
    if (
        pooled["dp1"]["log_loss"] >= pooled["dp0"]["log_loss"]
        and pooled["dp1"]["brier"] >= pooled["dp0"]["brier"]
        and improved < 3
    ):
        return "CLOSE_RETROSPECTIVE_LANE"
    return "INCONCLUSIVE_NO_TUNING"


def _formal_from_context(context: _PreflightContext) -> dict:
    """Run DP0/DP1 only after the complete preflight and A_Y gate passed."""
    data = context.data
    folds = {}
    operational = {}
    pooled_labels = []
    pooled_dp0 = []
    pooled_dp1 = []
    pooled_operational_labels = []
    pooled_a_y = []
    pooled_operational = []

    for year in FOLDS:
        train_mask = data.season.lt(year) & data.primary_eligible
        validation_mask = data.season.eq(year) & data.primary_eligible
        dp0_train = data.loc[train_mask].copy()
        dp0_validation = data.loc[validation_mask].copy()
        dp1_train = data.loc[train_mask].copy()
        dp1_validation = data.loc[validation_mask].copy()
        assert_same_fold_inputs(
            dp0_train, dp1_train, dp0_validation, dp1_validation
        )

        dp0_probabilities = _fit(dp0_train, dp0_validation, DP0_FEATURES)
        dp1_probabilities = _fit(dp1_train, dp1_validation, DP1_FEATURES)
        labels = dp0_validation.result.to_numpy(dtype=int)
        dp0_metrics = _metric_dict(labels, dp0_probabilities)
        dp1_metrics = _metric_dict(labels, dp1_probabilities)
        expected = EXPECTED_FOLD_COUNTS[year]
        folds[year] = {
            "total_train": expected[0],
            "eligible_train": len(dp0_train),
            "total_validation": expected[2],
            "eligible_validation": len(dp0_validation),
            "dp0": dp0_metrics,
            "dp1": dp1_metrics,
            "delta": _metric_delta(dp1_metrics, dp0_metrics),
            "draw_diagnostic": _draw_diagnostic(
                labels, dp0_probabilities, dp1_probabilities
            ),
        }
        pooled_labels.append(labels)
        pooled_dp0.append(dp0_probabilities)
        pooled_dp1.append(dp1_probabilities)

        validation_all = data.loc[data.season.eq(year)].copy()
        eligible_ids = dp1_validation.match_id.astype(str).tolist()
        a_y = context.a_y[year]
        operational_probabilities = _operational_fallback(
            a_y_probabilities=a_y["probabilities"],
            a_y_ids=a_y["validation_ids"],
            dp1_probabilities=dp1_probabilities,
            dp1_ids=eligible_ids,
            validation_ids=validation_all.match_id.astype(str).tolist(),
            eligible_ids=eligible_ids,
        )
        operational_labels = validation_all.result.to_numpy(dtype=int)
        a_y_aligned = _align_predictions(
            a_y["probabilities"],
            a_y["validation_ids"],
            validation_all.match_id.astype(str).tolist(),
        )
        operational[year] = {
            "rows": len(validation_all),
            "a_y": _metric_dict(operational_labels, a_y_aligned),
            "fallback_dp1": _metric_dict(
                operational_labels, operational_probabilities
            ),
        }
        pooled_operational_labels.append(operational_labels)
        pooled_a_y.append(a_y_aligned)
        pooled_operational.append(operational_probabilities)

    labels = np.concatenate(pooled_labels)
    dp0 = np.concatenate(pooled_dp0)
    dp1 = np.concatenate(pooled_dp1)
    dp0_metrics = _metric_dict(labels, dp0)
    dp1_metrics = _metric_dict(labels, dp1)
    pooled = {
        "dp0": dp0_metrics,
        "dp1": dp1_metrics,
        "delta": _metric_delta(dp1_metrics, dp0_metrics),
        "draw_diagnostic": _draw_diagnostic(labels, dp0, dp1),
    }

    operational_labels = np.concatenate(pooled_operational_labels)
    a_y_probabilities = np.concatenate(pooled_a_y)
    fallback_probabilities = np.concatenate(pooled_operational)
    operational_pooled = {
        "a_y": _metric_dict(operational_labels, a_y_probabilities),
        "fallback_dp1": _metric_dict(
            operational_labels, fallback_probabilities
        ),
    }
    improved = sum(
        folds[year]["dp1"]["log_loss"] < folds[year]["dp0"]["log_loss"]
        for year in FOLDS
    )
    return {
        "status": "FORMAL_DRAW_PROPENSITY_EVALUATION_COMPLETE",
        "artifact_sha256": context.public.artifact_sha256,
        "artifact_sha_gate": "PASS",
        "baseline_sanity": "PASS",
        "a_y_log_loss": context.public.a_y_log_loss,
        "fold_counts": context.public.fold_counts,
        "folds": folds,
        "pooled": pooled,
        "improved_log_loss_folds": improved,
        "operational": operational,
        "operational_pooled": operational_pooled,
        "decision": frozen_decision(folds, pooled),
        "diagnostics_are_decision_inputs": False,
        "existing_baseline_prediction_reused": False,
        "feature_changes": False,
        "parameter_changes": False,
        "tuning": "NOT RUN",
        "adaptive_follow_up": "NOT RUN",
    }


def render_evaluation_markdown(result: dict) -> str:
    """Render the future formal result deterministically, without timestamps."""
    lines = [
        "# Team Draw Propensity Evaluation",
        "",
        f"Artifact SHA-256: `{result['artifact_sha256']}`",
        f"Artifact SHA gate: **{result['artifact_sha_gate']}**",
        f"A_Y baseline sanity: **{result['baseline_sanity']}**",
        "",
        "## A_Y fold Log Loss",
        "",
        "| Season | A_Y Log Loss |",
        "|---:|---:|",
    ]
    for year in FOLDS:
        lines.append(f"| {year} | {result['a_y_log_loss'][year]!r} |")
    lines.extend([
        "",
        "## Primary matched fold results",
        "",
        "| Season | Total train | Eligible train | Total validation | Eligible validation | DP0 Accuracy | DP0 Log Loss | DP0 Brier | DP1 Accuracy | DP1 Log Loss | DP1 Brier | Delta Accuracy | Delta Log Loss | Delta Brier |",
        "|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ])
    for year in FOLDS:
        fold = result["folds"][year]
        dp0, dp1, delta = fold["dp0"], fold["dp1"], fold["delta"]
        lines.append(
            f"| {year} | {fold['total_train']} | {fold['eligible_train']} | "
            f"{fold['total_validation']} | {fold['eligible_validation']} | "
            f"{dp0['accuracy']!r} | {dp0['log_loss']!r} | {dp0['brier']!r} | "
            f"{dp1['accuracy']!r} | {dp1['log_loss']!r} | {dp1['brier']!r} | "
            f"{delta['accuracy']!r} | {delta['log_loss']!r} | {delta['brier']!r} |"
        )
    pooled = result["pooled"]
    lines.extend([
        "",
        "## Primary matched pooled result",
        "",
        "| Population | Accuracy | Log Loss | Brier | n |",
        "|---|---:|---:|---:|---:|",
        f"| DP0 | {pooled['dp0']['accuracy']!r} | {pooled['dp0']['log_loss']!r} | {pooled['dp0']['brier']!r} | {pooled['dp0']['count']} |",
        f"| DP1 | {pooled['dp1']['accuracy']!r} | {pooled['dp1']['log_loss']!r} | {pooled['dp1']['brier']!r} | {pooled['dp1']['count']} |",
        f"| Delta (DP1 - DP0) | {pooled['delta']['accuracy']!r} | {pooled['delta']['log_loss']!r} | {pooled['delta']['brier']!r} | - |",
        "",
        f"DP1 Log Loss improved folds: **{result['improved_log_loss_folds']} / 5**",
        "",
        "## Operational full-validation diagnostic",
        "",
        "| Season | Rows | A_Y Accuracy | A_Y Log Loss | A_Y Brier | Fallback-DP1 Accuracy | Fallback-DP1 Log Loss | Fallback-DP1 Brier |",
        "|---:|---:|---:|---:|---:|---:|---:|---:|",
    ])
    for year in FOLDS:
        row = result["operational"][year]
        a_y, fallback = row["a_y"], row["fallback_dp1"]
        lines.append(
            f"| {year} | {row['rows']} | {a_y['accuracy']!r} | {a_y['log_loss']!r} | {a_y['brier']!r} | "
            f"{fallback['accuracy']!r} | {fallback['log_loss']!r} | {fallback['brier']!r} |"
        )
    op = result["operational_pooled"]
    lines.extend([
        "",
        "### Operational pooled",
        "",
        "| Population | Accuracy | Log Loss | Brier | n |",
        "|---|---:|---:|---:|---:|",
        f"| A_Y | {op['a_y']['accuracy']!r} | {op['a_y']['log_loss']!r} | {op['a_y']['brier']!r} | {op['a_y']['count']} |",
        f"| Fallback-DP1 | {op['fallback_dp1']['accuracy']!r} | {op['fallback_dp1']['log_loss']!r} | {op['fallback_dp1']['brier']!r} | {op['fallback_dp1']['count']} |",
        "",
        "## Draw diagnostics",
        "",
        "```json",
        json.dumps(
            {
                "folds": {
                    str(year): result["folds"][year]["draw_diagnostic"]
                    for year in FOLDS
                },
                "pooled": pooled["draw_diagnostic"],
            },
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
        ),
        "```",
        "",
        "Draw diagnostics and operational metrics do not enter the decision.",
        "",
        "## Final decision",
        "",
        f"**{result['decision']}**",
        "",
        "feature changes = **NO**",
        "parameter changes = **NO**",
        "tuning = **NOT RUN**",
        "adaptive follow-up = **NOT RUN**",
        "existing baseline prediction reused = **NO**",
        "",
    ])
    return "\n".join(lines)


def write_evaluation_markdown(
    result: dict, path: str | Path = EVALUATION_DOC_PATH
) -> Path:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        render_evaluation_markdown(result), encoding="utf-8", newline="\n"
    )
    return output


def formal_evaluate(*, write_report: bool = True, **kwargs) -> dict:
    """Run the separately authorized one-shot formal evaluation."""
    context = _preflight_context(**kwargs)
    result = _formal_from_context(context)
    if write_report:
        write_evaluation_markdown(result)
    return result


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--preflight", action="store_true", help="run preflight only")
    mode.add_argument("--formal", action="store_true", help="run the frozen formal evaluation")
    parser.add_argument(
        "--confirm-one-shot",
        action="store_true",
        help="required with --formal to prevent accidental DP1 execution",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.formal != args.confirm_one_shot:
        parser.error("formal execution requires both explicit one-shot flags")
    if args.formal:
        result = formal_evaluate()
        print(result["status"])
        print(result["decision"])
        return 0

    result = preflight()
    print(result.status)
    print(f"ARTIFACT_SHA={result.artifact_sha256}")
    print(f"SCHEMA_IDENTITY={result.schema_identity_gate}")
    print(f"ELIGIBLE_COUNTS={result.eligible_counts_gate}")
    for year in FOLDS:
        print(f"A_Y_{year}_LOG_LOSS={result.a_y_log_loss[year]!r}")
    print(f"A_Y_GATE={result.a_y_gate}")
    print("FORMAL_DRAW_PROPENSITY_EVALUATION_NOT_RUN")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
