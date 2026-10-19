"""Driver tests with fictional matches only. Never load real data."""
from copy import deepcopy
import json
import socket

import numpy as np
import pandas as pd
import pytest

from src.modeling import nn_v2_offsets as o
from src.modeling import nn_v2_training as d


@pytest.fixture(autouse=True)
def no_external(monkeypatch):
    def denied(*args, **kwargs):
        raise AssertionError("Synthetic tests may not fetch data")
    monkeypatch.setattr(socket.socket, "connect", denied)
    monkeypatch.setattr(d.loader, "load_source", denied)


def prepared():
    rows = []
    for year in range(2015, 2026):
        for j in range(6):
            hg, ag = [(0, 1), (1, 1), (2, 0)][j % 3]
            rows.append(dict(match_id=f"synthetic-{year}-{j}", season=year,
                match_date=pd.Timestamp(year, 2, j+1), kickoff_time="19:00",
                home_team_id="synthetic-home", away_team_id="synthetic-away",
                home_score=hg, away_score=ag, result=j % 3))
    frame = o.prepare_history(pd.DataFrame(rows))
    plan = {"folds": [{"target_year": y, "training_ids": frame.loc[frame.season.lt(y), "match_id"].tolist(),
                       "target_ids": frame.loc[frame.season.eq(y), "match_id"].tolist()} for y in range(2017, 2026)],
            "final_baseline_fit_ids": frame.match_id.tolist(),
            "residual_scaler_fit_ids": frame.loc[frame.season.ge(2017), "match_id"].tolist()}
    return frame, plan


def test_synthetic_single_fit_budget_and_independent_readback(tmp_path):
    frame, plan = prepared(); before = frame.copy(deep=True)
    counts = d.fit_once(frame, plan, tmp_path)
    assert counts == dict(crossfit_baseline=9, final_baseline=1, residual_nn=1,
                          logistic_fit_calls=10, scaler_fit_calls=11, adam_updates=200)
    assert d.verify_models(tmp_path)["model_probability_max_abs_difference"] == 0
    assert d.verify_models(tmp_path)["offset_rows"] == 54
    assert len(pd.read_csv(tmp_path/"training-loss.csv")) == 200
    assert len(list((tmp_path/"fit-events").glob("*-started.json"))) == 11
    assert len(list((tmp_path/"fit-events").glob("*-succeeded.json"))) == 11
    assert all(json.loads(p.read_bytes())["training_rows"] == 54
               for p in [(tmp_path/"residual/artifact.json")])
    pd.testing.assert_frame_equal(frame, before)
    with pytest.raises(FileExistsError):
        d.fit_once(frame, plan, tmp_path)


@pytest.mark.parametrize("edit", ["training_year", "target_ids", "residual_ids", "final_ids"])
def test_invalid_id_contract_stops_without_silent_join(tmp_path, edit):
    frame, plan = prepared()
    if edit == "training_year": plan["folds"][0]["training_ids"].append(plan["folds"][0]["target_ids"][0])
    if edit == "target_ids": plan["folds"][0]["target_ids"].reverse()
    if edit == "residual_ids": plan["residual_scaler_fit_ids"].reverse()
    if edit == "final_ids": plan["final_baseline_fit_ids"].reverse()
    with pytest.raises(ValueError):
        d.fit_once(frame, plan, tmp_path)


def test_fit_warning_stops_and_keeps_partial_receipts(tmp_path, monkeypatch):
    import warnings
    frame, plan = prepared()
    original = d.nn.ResidualNN.fit
    def warned(self, *args):
        warnings.warn("synthetic fit warning", UserWarning)
        return original(self, *args)
    monkeypatch.setattr(d.nn.ResidualNN, "fit", warned)
    with pytest.raises(ValueError, match="Fit warning"):
        d.fit_once(frame, plan, tmp_path)
    assert (tmp_path/"fit-events/11-started.json").exists()
    assert not (tmp_path/"residual").exists()


def test_exclusive_receipt_never_overwrites(tmp_path):
    marker = tmp_path/"attempt.json"
    d.write_json(marker, {"state": "STARTED"})
    original = marker.read_bytes()
    with pytest.raises(FileExistsError): d.write_json(marker, {"state": "STARTED"})
    assert marker.read_bytes() == original


def test_symlink_parent_rejected(tmp_path):
    # Does not require symlink privileges on Windows: use the stat contract.
    from unittest.mock import patch
    with patch.object(d.Path, "is_symlink", return_value=True), pytest.raises(ValueError):
        d.plain_parent(tmp_path)
