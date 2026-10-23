
"""
Evaluation service for OmaxasAI.

Stores benchmark results and summarizes model quality.
It does not call an AI model or calculate monetary costs.
"""

from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Avg, Count, Q

from ..models import AIRequest, EvaluationResult, ModelRegistry


class EvaluationServiceError(ValueError):
    """Raised when evaluation data is invalid."""


def _validate_non_negative_integer(value, field_name):
    """Validate optional token counts and latency measurements."""

    if value is None:
        return None

    if isinstance(value, bool):
        raise EvaluationServiceError(
            f"{field_name} must be a non-negative integer."
        )

    if not isinstance(value, int) or value < 0:
        raise EvaluationServiceError(
            f"{field_name} must be a non-negative integer."
        )

    return value


def _validate_score(score):
    """Validate a benchmark score between 0 and 100."""

    if score is None:
        return None

    try:
        value = Decimal(str(score))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise EvaluationServiceError(
            "Score must be a valid number between 0 and 100."
        ) from exc

    if not value.is_finite() or not Decimal("0") <= value <= Decimal("100"):
        raise EvaluationServiceError(
            "Score must be between 0 and 100."
        )

    return value.quantize(Decimal("0.01"))


@transaction.atomic
def record_evaluation(
    *,
    model: ModelRegistry,
    benchmark_name: str,
    task_category: str = AIRequest.TaskCategory.GENERAL,
    score=None,
    passed: bool | None = None,
    latency_ms: int | None = None,
    input_tokens: int | None = None,
    output_tokens: int | None = None,
    result_summary: str = "",
) -> EvaluationResult:
    """
    Record a benchmark result for a registered AI model.

    The evaluation must have been performed by a trusted
    benchmark or evaluation process before calling this function.

    Args:
        model: Registered AI model being evaluated.
        benchmark_name: Name of the benchmark or test suite.
        task_category: Type of task being tested.
        score: Optional numeric score from 0 to 100.
        passed: Optional pass/fail result from the test.
        latency_ms: Optional measured response latency.
        input_tokens: Optional input token count.
        output_tokens: Optional output token count.
        result_summary: Brief description of the result.

    Returns:
        The saved EvaluationResult instance.
    """

    if not isinstance(model, ModelRegistry):
        raise EvaluationServiceError(
            "A registered AI model is required."
        )

    if not isinstance(benchmark_name, str):
        raise EvaluationServiceError(
            "Benchmark name must be text."
        )

    benchmark_name = benchmark_name.strip()

    if not benchmark_name:
        raise EvaluationServiceError(
            "Benchmark name cannot be empty."
        )

    if len(benchmark_name) > 150:
        raise EvaluationServiceError(
            "Benchmark name cannot exceed 150 characters."
        )

    valid_categories = {
        value for value, _label in AIRequest.TaskCategory.choices
    }

    if task_category not in valid_categories:
        raise EvaluationServiceError(
            "Unsupported evaluation task category."
        )

    if passed is not None and not isinstance(passed, bool):
        raise EvaluationServiceError(
            "Passed must be True, False, or None."
        )

    if not isinstance(result_summary, str):
        raise EvaluationServiceError(
            "Result summary must be text."
        )

    result = EvaluationResult(
        model=model,
        benchmark_name=benchmark_name,
        task_category=task_category,
        score=_validate_score(score),
        passed=passed,
        latency_ms=_validate_non_negative_integer(
            latency_ms,
            "latency_ms",
        ),
        input_tokens=_validate_non_negative_integer(
            input_tokens,
            "input_tokens",
        ),
        output_tokens=_validate_non_negative_integer(
            output_tokens,
            "output_tokens",
        ),
        result_summary=result_summary.strip()[:10000],
    )

    try:
        result.full_clean()
        result.save()
    except ValidationError as exc:
        raise EvaluationServiceError(
            "Evaluation data failed model validation."
        ) from exc

    return result


def get_model_evaluation_summary(
    *,
    model: ModelRegistry,
    task_category: str | None = None,
) -> dict:
    """
    Return quality and latency statistics for a registered model.

    Only results with a numeric score contribute to average_score.
    Passing or failing is counted only when that result was recorded.
    """

    if not isinstance(model, ModelRegistry):
        raise EvaluationServiceError(
            "A registered AI model is required."
        )

    queryset = EvaluationResult.objects.filter(model=model)

    if task_category is not None:
        valid_categories = {
            value for value, _label in AIRequest.TaskCategory.choices
        }

        if task_category not in valid_categories:
            raise EvaluationServiceError(
                "Unsupported evaluation task category."
            )

        queryset = queryset.filter(task_category=task_category)

    summary = queryset.aggregate(
        total_evaluations=Count("id"),
        average_score=Avg("score"),
        average_latency_ms=Avg("latency_ms"),
        passed_count=Count("id", filter=Q(passed=True)),
        failed_count=Count("id", filter=Q(passed=False)),
    )

    average_score = summary["average_score"]
    average_latency = summary["average_latency_ms"]

    return {
        "model_id": model.pk,
        "model_name": model.name,
        "task_category": task_category,
        "total_evaluations": summary["total_evaluations"],
        "average_score": (
            round(float(average_score), 2)
            if average_score is not None
            else None
        ),
        "average_latency_ms": (
            round(float(average_latency), 2)
            if average_latency is not None
            else None
        ),
        "passed_count": summary["passed_count"],
        "failed_count": summary["failed_count"],
    }

