"""A malformed config fails fast at the boundary with a clear message, not with
a KeyError mid-run after a model has already been called."""

from __future__ import annotations

import pytest
import yaml
from click.testing import CliRunner

from agent_pipeline.cli import main
from agent_pipeline.config import (
    ConfigError,
    validate_pipeline_config,
    validate_policy_config,
)

ROOT = __import__("pathlib").Path(__file__).resolve().parents[1]


def _pipeline() -> dict:
    return yaml.safe_load((ROOT / "config" / "pipeline.yaml").read_text())


def _policy() -> dict:
    return yaml.safe_load((ROOT / "config" / "policy.yaml").read_text())


# --- The shipped configs are valid -----------------------------------------


def test_shipped_configs_validate():
    validate_pipeline_config(_pipeline())
    validate_policy_config(_policy())


# --- Pipeline config --------------------------------------------------------


def test_missing_models_section_is_rejected():
    cfg = _pipeline()
    del cfg["models"]
    with pytest.raises(ConfigError, match="models"):
        validate_pipeline_config(cfg, "pipeline.yaml")


def test_missing_reviewer_model_is_rejected():
    cfg = _pipeline()
    del cfg["models"]["reviewer"]
    with pytest.raises(ConfigError, match="reviewer"):
        validate_pipeline_config(cfg)


def test_missing_llm_or_audit_section_is_rejected():
    cfg = _pipeline()
    del cfg["llm"]
    with pytest.raises(ConfigError, match="llm"):
        validate_pipeline_config(cfg)


def test_non_mapping_pipeline_is_rejected():
    with pytest.raises(ConfigError, match="mapping"):
        validate_pipeline_config(["not", "a", "dict"])


# --- Policy config ----------------------------------------------------------


def test_missing_action_space_is_rejected():
    cfg = _policy()
    del cfg["action_space"]
    with pytest.raises(ConfigError, match="action_space"):
        validate_policy_config(cfg)


def test_empty_action_space_is_rejected():
    cfg = _policy()
    cfg["action_space"] = []
    with pytest.raises(ConfigError, match="action_space"):
        validate_policy_config(cfg)


def test_out_of_range_min_confidence_is_rejected():
    cfg = _policy()
    cfg["min_confidence"] = 1.5
    with pytest.raises(ConfigError, match="min_confidence"):
        validate_policy_config(cfg)


# --- CLI surfaces a clean error, no traceback -------------------------------


def test_cli_run_reports_a_broken_config(tmp_path):
    doc = tmp_path / "doc.txt"
    doc.write_text("hello", encoding="utf-8")
    bad = tmp_path / "pipeline.yaml"
    bad.write_text("llm: {}\naudit: {}\n", encoding="utf-8")  # no models
    result = CliRunner().invoke(
        main,
        ["run", "--input", str(doc), "--config", str(bad), "--policy", "config/policy.yaml"],
    )
    assert result.exit_code != 0
    assert "Invalid config" in result.output
    assert "models" in result.output
