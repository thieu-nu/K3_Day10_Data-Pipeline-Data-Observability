from __future__ import annotations

from typing import TYPE_CHECKING, Any

__all__ = [
    "EvaluationBundle",
    "EvaluationError",
    "JudgeParseError",
    "JudgeVerdict",
    "TestSetValidationError",
    "build_test_set",
    "evaluate_pipeline",
    "load_or_build_test_set",
    "load_test_set",
    "test_set_fingerprint",
    "validate_test_set",
]

_METRICS_EXPORTS = frozenset(
    {"EvaluationBundle", "EvaluationError", "JudgeParseError", "JudgeVerdict", "evaluate_pipeline"}
)
_TESTSET_EXPORTS = frozenset(set(__all__) - set(_METRICS_EXPORTS))

if TYPE_CHECKING:  # pragma: no cover
    from .metrics import (
        EvaluationBundle,
        EvaluationError,
        JudgeParseError,
        JudgeVerdict,
        evaluate_pipeline,
    )
    from .testset import (
        TestSetValidationError,
        build_test_set,
        load_or_build_test_set,
        load_test_set,
        test_set_fingerprint,
        validate_test_set,
    )


def __getattr__(name: str) -> Any:
    """Re-export lazily so that importing the test-set builder does not drag in the
    metrics dependency chain (datasets, sentence-transformers, langchain providers).

    `from evaluation import evaluate_pipeline` keeps working exactly as before.
    """
    if name in _METRICS_EXPORTS:
        from . import metrics

        return getattr(metrics, name)
    if name in _TESTSET_EXPORTS:
        from . import testset

        return getattr(testset, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:
    return sorted(__all__)
