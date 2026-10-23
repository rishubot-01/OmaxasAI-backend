"""
OmaxasAI Model Router.

Selects an available AI model based on task, Think mode,
capabilities, provider credentials, evaluation quality,
latency, and self-hosted model availability.

API calls are handled by the AI service layer.
"""

import os
from dataclasses import dataclass

from django.db.models import Avg, Q

from ..models import AIRequest, ModelRegistry
from .task_classifier import classify_task


class NoSuitableModelError(RuntimeError):
    """Raised when no registered model satisfies the request."""


@dataclass(frozen=True)
class ModelRoute:
    """The model selection decision returned by the router."""

    model: ModelRegistry
    category: str
    mode: str
    web_search: bool
    fallback_models: tuple[ModelRegistry, ...]


# Keep these names consistent with ai_service.py.
# Store environment-variable names, never API key values,
# in ModelRegistry.credential_env_var.
PROVIDER_ENV_VARS = {
    "openai": "OPENAI_API_KEY",
    "gemini": "GEMINI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "xai": "XAI_API_KEY",
    "deepseek": "DEEPSEEK_API_KEY",
    "mistral": "MISTRAL_API_KEY",
    "cohere": "COHERE_API_KEY",
    "groq": "GROQ_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
    "nvidia": "NVIDIA_NIM_API_KEY",
    "together": "TOGETHERAI_API_KEY",
    "fireworks": "FIREWORKS_API_KEY",
    "cerebras": "CEREBRAS_API_KEY",
    "perplexity": "PERPLEXITYAI_API_KEY",
    "huggingface": "HUGGINGFACE_API_KEY",
    "custom": "OMAXASAI_CUSTOM_API_KEY",
}


COMING_SOON_STATUSES = {
    "coming soon",
    "coming_soon",
    "not_available",
}


CATEGORY_CAPABILITIES = {
    "coding": {"coding", "code"},
    "research": {"research"},
    "reasoning": {"reasoning", "think"},
    "writing": {"writing"},
    "vision": {"vision", "image"},
    "general": {"chat", "general", "text"},
    "other": set(),
}


def _get_capabilities(model: ModelRegistry) -> set[str]:
    """Return a normalized set of model capabilities."""

    capabilities = model.capabilities

    if not isinstance(capabilities, list):
        return set()

    return {
        item.strip().lower()
        for item in capabilities
        if isinstance(item, str) and item.strip()
    }


def _is_coming_soon(model: ModelRegistry) -> bool:
    """Return whether the model is marked Coming Soon."""

    config = (
        model.config
        if isinstance(model.config, dict)
        else {}
    )

    configured_status = str(
        config.get("status", "")
    ).strip().lower()

    return (
        config.get("coming_soon") is True
        or configured_status in COMING_SOON_STATUSES
    )


def _credentials_available(model: ModelRegistry) -> bool:
    """
    Check whether required credentials or endpoints are configured.

    External providers require an API key.

    Self-hosted models require an endpoint. Their credentials
    are optional unless credential_env_var is explicitly configured.
    """

    configured_env_var = (
        model.credential_env_var.strip()
        if model.credential_env_var
        else ""
    )

    is_self_hosted = (
        model.backend_type
        == ModelRegistry.BackendType.SELF_HOSTED
    )

    if is_self_hosted:
        endpoint = (
            (model.endpoint_url or "").strip()
            or os.getenv(
                "SELF_HOSTED_MODEL_BASE_URL",
                "",
            ).strip()
            or os.getenv(
                "OMAXASAI_SELF_HOSTED_BASE_URL",
                "",
            ).strip()
        )

        if not endpoint:
            return False

        # Match ai_service.py: self-hosted authentication is optional
        # unless the registry explicitly names a credential variable.
        if configured_env_var:
            return bool(
                os.getenv(configured_env_var, "").strip()
            )

        return True

    # A model-specific environment-variable name takes precedence.
    # If it is not populated, allow the standard provider variable.
    candidate_names = []

    for env_name in (
        configured_env_var,
        PROVIDER_ENV_VARS.get(
            model.provider.strip().lower(),
            "",
        ),
    ):
        if env_name and env_name not in candidate_names:
            candidate_names.append(env_name)

    return any(
        bool(os.getenv(env_name, "").strip())
        for env_name in candidate_names
    )


def _get_quality_score(model: ModelRegistry) -> float:
    """
    Read the average score populated by the router's aggregate query.

    Models without evaluated scores receive a neutral score of 0.
    """

    score = getattr(
        model,
        "_route_quality_score",
        None,
    )

    if score is None:
        return 0.0

    return float(score)


def _get_latency_score(model: ModelRegistry) -> float:
    """
    Read the average evaluation latency populated by the aggregate query.

    Unknown latency is placed after models with measured latency
    when their quality scores are equal.
    """

    latency = getattr(
        model,
        "_route_latency_ms",
        None,
    )

    if latency is None:
        return float("inf")

    try:
        latency = float(latency)
    except (TypeError, ValueError, OverflowError):
        return float("inf")

    if latency < 0:
        return float("inf")

    return latency


def _ordered_candidates(
    candidates: list[ModelRegistry],
) -> list[ModelRegistry]:
    """
    Rank candidates by quality, measured latency, priority, and name.

    1. Higher evaluation quality comes first.
    2. Lower measured latency breaks quality ties.
    3. Lower numerical priority breaks remaining ties.
    4. Model name provides deterministic ordering.
    """

    return sorted(
        candidates,
        key=lambda model: (
            -_get_quality_score(model),
            _get_latency_score(model),
            model.priority,
            model.name.casefold(),
        ),
    )


def _load_candidates(category: str) -> list[ModelRegistry]:
    """
    Fetch active models and their category-specific evaluation metrics.

    Both metrics are calculated in one database query rather than
    making a separate aggregate query for every model.
    """

    candidates = ModelRegistry.objects.filter(
        active=True,
    ).annotate(
        _route_quality_score=Avg(
            "evaluation_results__score",
            filter=Q(
                evaluation_results__task_category=category,
                evaluation_results__score__isnull=False,
            ),
        ),
        _route_latency_ms=Avg(
            "evaluation_results__latency_ms",
            filter=Q(
                evaluation_results__task_category=category,
                evaluation_results__latency_ms__isnull=False,
            ),
        ),
    )

    # Apply configuration availability checks before routing.
    return [
        model
        for model in candidates
        if not _is_coming_soon(model)
        and _credentials_available(model)
    ]


def choose_model(
    message: str,
    *,
    mode: str = "auto",
    web_search: bool = False,
    has_images: bool = False,
    allow_external: bool = True,
    stream: bool = True,
) -> ModelRoute:
    """
    Select a primary model and compatible fallback candidates.

    Args:
        message: The user's text prompt.
        mode: "auto" or "think".
        web_search: Whether the request needs web retrieval.
        has_images: Whether the request contains image input.
        allow_external: Whether external providers are permitted.
        stream: Whether streaming support is required.

    Returns:
        A ModelRoute containing the selected model and fallbacks.

    Raises:
        ValueError: If the requested mode is unsupported.
        NoSuitableModelError: If no eligible model is configured.
    """

    if not isinstance(mode, str):
        raise ValueError(
            "Unsupported mode. Use 'auto' or 'think'."
        )

    mode = mode.strip().lower()

    valid_modes = {
        AIRequest.ModeChoices.AUTO,
        AIRequest.ModeChoices.THINK,
    }

    if mode not in valid_modes:
        raise ValueError(
            "Unsupported mode. Use 'auto' or 'think'."
        )

    category = classify_task(
        message,
        has_images=has_images,
        web_search=web_search,
    )

    # Load model metrics together, avoiding per-model quality queries.
    candidates = _load_candidates(category)

    # Enforce application-level privacy restrictions.
    if not allow_external:
        candidates = [
            model
            for model in candidates
            if (
                model.backend_type
                == ModelRegistry.BackendType.SELF_HOSTED
            )
        ]

    # Image requests require vision capability.
    if has_images:
        candidates = [
            model
            for model in candidates
            if (
                model.supports_vision
                or bool(
                    _get_capabilities(model)
                    & CATEGORY_CAPABILITIES["vision"]
                )
            )
        ]

    # Apply streaming capability requirements only when streaming
    # was requested by the caller.
    if stream:
        candidates = [
            model
            for model in candidates
            if model.supports_streaming
        ]

    # Think mode and reasoning tasks require reasoning capability.
    requires_reasoning = (
        mode == AIRequest.ModeChoices.THINK
        or category == AIRequest.TaskCategory.REASONING
    )

    if requires_reasoning:
        candidates = [
            model
            for model in candidates
            if (
                _get_capabilities(model)
                & CATEGORY_CAPABILITIES["reasoning"]
            )
        ]

    if not candidates:
        raise NoSuitableModelError(
            "No eligible AI model is available. Check active model "
            "records, availability status, provider credentials, endpoint "
            "configuration, streaming support, and model capabilities."
        )

    # Prefer models explicitly registered for the detected task.
    category_capabilities = CATEGORY_CAPABILITIES.get(
        category,
        set(),
    )

    category_matches = [
        model
        for model in candidates
        if (
            _get_capabilities(model)
            & category_capabilities
        )
    ]

    if category_matches:
        candidates = category_matches

    # Highest-quality candidate first, with measured latency as
    # a tie-breaker. Remaining candidates become fallbacks.
    ranked = _ordered_candidates(candidates)

    return ModelRoute(
        model=ranked[0],
        category=category,
        mode=mode,
        web_search=web_search,
        fallback_models=tuple(ranked[1:]),
    )