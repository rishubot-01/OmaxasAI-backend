
"""
Fallback service for OmaxasAI.

Tries eligible AI models in order until one succeeds or
the retry limit is reached.

This module does not make provider API calls itself.
"""

import logging
from dataclasses import dataclass
from typing import Any, Callable, Iterable, TypeVar


logger = logging.getLogger(__name__)

T = TypeVar("T")


class NoEligibleModelsError(RuntimeError):
    """Raised when no candidate models are available."""


class AllModelsFailedError(RuntimeError):
    """Raised when every attempted model fails."""


@dataclass(frozen=True)
class FallbackExecutionResult:
    """Result of a successful primary or fallback attempt."""

    model: Any
    response: Any
    fallback_used: bool
    attempts: int


def execute_with_fallback(
    models: Iterable[Any],
    invoke: Callable[[Any], T],
    *,
    max_attempts: int | None = None,
    non_retryable_exceptions: tuple[type[BaseException], ...] = (),
) -> FallbackExecutionResult:
    """
    Attempt eligible models in priority order.

    Args:
        models:
            Ordered model candidates from the model router.

        invoke:
            A callable that accepts a model and performs one
            generation attempt.

        max_attempts:
            Optional limit on total attempts, including the primary.
            Defaults to the number of supplied candidates.

        non_retryable_exceptions:
            Exception types that should stop fallback immediately.
            For example, configuration or invalid-request errors.

    Returns:
        FallbackExecutionResult containing the successful model,
        response, fallback status and number of attempts.

    Raises:
        NoEligibleModelsError:
            If the candidate list is empty.

        AllModelsFailedError:
            If every attempted model fails.
    """

    candidates = list(models)

    if not candidates:
        raise NoEligibleModelsError(
            "No eligible AI models were provided."
        )

    if max_attempts is None:
        attempt_limit = len(candidates)
    else:
        if max_attempts < 1:
            raise ValueError("max_attempts must be at least 1.")

        attempt_limit = min(max_attempts, len(candidates))

    last_error = None

    for attempt_index, model in enumerate(
        candidates[:attempt_limit],
        start=1,
    ):
        provider = getattr(model, "provider", "unknown")
        model_id = getattr(model, "model_id", "unknown")

        try:
            response = invoke(model)

            logger.info(
                "AI model attempt succeeded. provider=%s model=%s",
                provider,
                model_id,
            )

            return FallbackExecutionResult(
                model=model,
                response=response,
                fallback_used=attempt_index > 1,
                attempts=attempt_index,
            )

        except non_retryable_exceptions:
            # Invalid input or configuration problems should not
            # automatically trigger requests to other providers.
            raise

        except Exception as exc:
            last_error = exc

            # Do not log prompts, credentials, or exception messages
            # that might contain sensitive provider response data.
            logger.warning(
                "AI model attempt failed. provider=%s model=%s "
                "attempt=%s",
                provider,
                model_id,
                attempt_index,
                exc_info=True,
            )

    raise AllModelsFailedError(
        "All eligible AI model attempts failed."
    ) from last_error

