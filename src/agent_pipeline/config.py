"""Fail-fast validation of the YAML config files.

A malformed ``pipeline.yaml`` or ``policy.yaml`` should fail at the boundary with
a clear message — not with a ``KeyError`` deep inside a run, after a model has
already been called. These Pydantic models validate only the keys the pipeline
actually depends on; everything else is passed through (``extra="allow"``), so
comments, the ``web`` block, provider-specific settings, and future additions do
not need to be enumerated here.

Validation does **not** change the runtime representation: the pipeline still
consumes plain dicts. :func:`validate_pipeline_config` / :func:`validate_policy_config`
are a gate, called once on load, raising :class:`ConfigError` on a real mistake.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError


class ConfigError(ValueError):
    """A config file is missing a required key or has a value of the wrong type."""


class _ModelsConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    planner: str = Field(min_length=1)
    worker: str = Field(min_length=1)
    reviewer: str = Field(min_length=1)


class _PipelineConfig(BaseModel):
    """The keys the orchestrator reads without a default (would ``KeyError``)."""

    model_config = ConfigDict(extra="allow")

    models: _ModelsConfig
    llm: dict[str, Any]
    audit: dict[str, Any]


class _PolicyConfig(BaseModel):
    """The guardrails the reviewer and planner require."""

    model_config = ConfigDict(extra="allow")

    action_space: list[str] = Field(min_length=1)
    min_confidence: float = Field(default=0.6, ge=0.0, le=1.0)


def _format(exc: ValidationError, source: str) -> str:
    lines = [f"Invalid config in {source}:"]
    for err in exc.errors():
        loc = ".".join(str(p) for p in err["loc"]) or "(root)"
        lines.append(f"  - {loc}: {err['msg']}")
    return "\n".join(lines)


def validate_pipeline_config(data: Any, source: str = "pipeline config") -> None:
    """Raise :class:`ConfigError` if the pipeline config is unusable."""
    if not isinstance(data, dict):
        raise ConfigError(f"Invalid config in {source}: expected a mapping at the top level.")
    try:
        _PipelineConfig.model_validate(data)
    except ValidationError as exc:
        raise ConfigError(_format(exc, source)) from exc


def validate_policy_config(data: Any, source: str = "policy config") -> None:
    """Raise :class:`ConfigError` if the policy config is unusable."""
    if not isinstance(data, dict):
        raise ConfigError(f"Invalid config in {source}: expected a mapping at the top level.")
    try:
        _PolicyConfig.model_validate(data)
    except ValidationError as exc:
        raise ConfigError(_format(exc, source)) from exc
