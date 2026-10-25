"""
OmaxasAI AI service.

Routes prompts to registered AI models through LiteLLM.
Supports automatic routing, explicitly selected models, and
automatic failover when a model fails or exceeds its timeout.

Provider credentials are read from environment variables.
Monetary cost is deliberately not tracked.
"""

import logging
import os
from time import perf_counter

from ..models import AIRequest, ModelRegistry
from .model_router import (
    PROVIDER_ENV_VARS,
    NoSuitableModelError,
    choose_model,
)


logger = logging.getLogger(__name__)


class AIServiceError(RuntimeError):
    """Raised when OmaxasAI cannot generate a response."""


class AIServiceConfigurationError(AIServiceError):
    """Raised when a required AI integration is misconfigured."""


SYSTEM_PROMPT = """
You are OmaxasAI, a helpful and reliable AI assistant.

Guidelines:
- Respond in the language used by the user whenever practical.
- Give accurate, clear, and useful answers.
- For coding requests, provide working code and explain important details.
- For research, distinguish verified facts from uncertainty.
- Never claim to have searched the web without a real search integration.
- Do not reveal private internal chain-of-thought.
- Do not claim to have performed actions you did not perform.
""".strip()


# LiteLLM provider prefixes.
LITELLM_PROVIDER_PREFIXES = {
    "openai": "",
    "gemini": "gemini/",
    "anthropic": "anthropic/",
    "xai": "xai/",
    "deepseek": "deepseek/",
    "mistral": "mistral/",
    "cohere": "cohere_chat/",
    "groq": "groq/",
    "openrouter": "openrouter/",
    "nvidia": "nvidia_nim/",
    "together": "together_ai/",
    "fireworks": "fireworks_ai/",
    "cerebras": "cerebras/",
    "perplexity": "perplexity/",
    "huggingface": "huggingface/",
}


STANDARD_PROVIDER_ENV_VARS = {
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
}


PROVIDER_ENV_ALIASES = {
    "gemini": (
        "GEMINI_API_KEY",
        "GOOGLE_API_KEY",
    ),
    "nvidia": (
        "NVIDIA_NIM_API_KEY",
        "NVIDIA_API_KEY",
    ),
    "huggingface": (
        "HF_TOKEN",
    ),
}


ALLOWED_MODEL_OPTIONS = {
    "temperature",
    "max_tokens",
    "max_completion_tokens",
    "top_p",
    "frequency_penalty",
    "presence_penalty",
    "seed",
}


# A single model attempt cannot be configured above 10 seconds.
MIN_TIMEOUT_SECONDS = 1
MAX_TIMEOUT_SECONDS = 10

DEFAULT_TIMEOUT_SECONDS = 10
DEFAULT_GEMINI_TIMEOUT_SECONDS = 10
DEFAULT_GEMINI_THINK_TIMEOUT_SECONDS = 10


def _get_field(value, field_name, default=None):
    """Read a field from a dictionary or response object."""

    if isinstance(value, dict):
        return value.get(field_name, default)

    return getattr(value, field_name, default)


def _get_model_config(model):
    """Return model configuration safely."""

    config = getattr(model, "config", None)

    return config if isinstance(config, dict) else {}


def _get_provider_name(model):
    """Return the normalized provider name."""

    provider = getattr(model, "provider", "")

    if not isinstance(provider, str):
        return ""

    return provider.strip().lower()


def _get_usage_value(usage, *field_names):
    """Extract token counts from dictionaries or response objects."""

    if usage is None:
        return None

    for field_name in field_names:
        value = _get_field(usage, field_name)

        if value is None or isinstance(value, bool):
            continue

        try:
            count = int(value)
        except (TypeError, ValueError, OverflowError):
            continue

        if count >= 0:
            return count

    return None


def _extract_text(content):
    """Convert supported model response formats to plain text."""

    if isinstance(content, str):
        return content.strip()

    if not isinstance(content, list):
        return ""

    parts = []

    for item in content:
        if isinstance(item, str):
            if item.strip():
                parts.append(item.strip())
            continue

        item_type = _get_field(item, "type")

        if item_type not in (None, "text", "output_text"):
            continue

        text_part = _get_field(item, "text")

        if isinstance(text_part, str) and text_part.strip():
            parts.append(text_part.strip())

    return "\n".join(parts).strip()


def _is_self_hosted_model(model):
    """Return whether the model uses the self-hosted backend."""

    return (
        getattr(model, "backend_type", None)
        == ModelRegistry.BackendType.SELF_HOSTED
    )


def _configuration_error(model, reason):
    """Create a configuration error without logging secrets or prompts."""

    logger.warning(
        "AI model configuration error. provider=%s model_id=%s reason=%s",
        _get_provider_name(model),
        getattr(model, "model_id", "") or "<missing>",
        reason,
    )

    return AIServiceConfigurationError(reason)


def _validate_model_availability(model):
    """Ensure the registered model is available for inference."""

    if not getattr(model, "active", False):
        raise _configuration_error(
            model,
            "The selected AI model is inactive.",
        )

    availability_status = getattr(
        model,
        "availability_status",
        "available",
    )

    if availability_status != "available":
        raise _configuration_error(
            model,
            "The selected AI model is not available for inference.",
        )


def _get_provider_credentials(model):
    """Resolve credentials from environment variables only."""

    provider = _get_provider_name(model)

    configured_env_var = str(
        getattr(model, "credential_env_var", "") or ""
    ).strip()

    candidate_names = []

    env_names = (
        configured_env_var,
        STANDARD_PROVIDER_ENV_VARS.get(provider, ""),
        PROVIDER_ENV_VARS.get(provider, ""),
        *PROVIDER_ENV_ALIASES.get(provider, ()),
    )

    for env_name in env_names:
        if env_name and env_name not in candidate_names:
            candidate_names.append(env_name)

    if _is_self_hosted_model(model):
        if configured_env_var:
            api_key = os.getenv(configured_env_var, "").strip()

            if not api_key:
                raise _configuration_error(
                    model,
                    "The configured self-hosted model credential is missing.",
                )

            return api_key

        # Some self-hosted OpenAI-compatible endpoints do not require
        # a real API key. Configure the endpoint separately.
        return "EMPTY"

    if not candidate_names:
        raise _configuration_error(
            model,
            "No credential environment variable is configured for this provider.",
        )

    for env_name in candidate_names:
        api_key = os.getenv(env_name, "").strip()

        if api_key:
            return api_key

    raise _configuration_error(
        model,
        "Provider credentials are missing. Checked environment "
        "variable names: " + ", ".join(candidate_names),
    )


def _get_litellm_model_name(model):
    """
    Resolve ModelRegistry.model_id to a LiteLLM model identifier.

    config["litellm_model"] takes precedence over model_id.
    Gemini's Google AI Studio route uses the gemini/ prefix.
    """

    config = _get_model_config(model)

    configured_model = config.get("litellm_model")

    if (
        isinstance(configured_model, str)
        and configured_model.strip()
    ):
        model_id = configured_model.strip()
    else:
        model_id = getattr(model, "model_id", "")

        model_id = (
            model_id.strip()
            if isinstance(model_id, str)
            else ""
        )

    if not model_id:
        raise _configuration_error(
            model,
            "The registered model has no configured model ID.",
        )

    provider = _get_provider_name(model)

    if provider == "gemini":
        if model_id.startswith("vertex_ai/"):
            raise _configuration_error(
                model,
                "The model ID uses Vertex AI routing, but this provider "
                "is configured for Gemini API-key authentication.",
            )

        if not model_id.startswith("gemini/"):
            model_id = f"gemini/{model_id}"

        return model_id

    # Do not change the model identifier of other providers when a
    # complete identifier is explicitly supplied in model config.
    if (
        isinstance(configured_model, str)
        and configured_model.strip()
    ):
        return model_id

    prefix = LITELLM_PROVIDER_PREFIXES.get(provider)

    if prefix is None or not prefix:
        return model_id

    if model_id.startswith(prefix):
        return model_id

    return f"{prefix}{model_id}"


def _get_model_endpoint(model):
    """Resolve the registered or provider-specific API endpoint."""

    provider = _get_provider_name(model)

    configured_endpoint = str(
        getattr(model, "endpoint_url", "") or ""
    ).strip()

    if _is_self_hosted_model(model):
        return (
            configured_endpoint
            or os.getenv(
                "SELF_HOSTED_MODEL_BASE_URL",
                "",
            ).strip()
            or os.getenv(
                "OMAXASAI_SELF_HOSTED_BASE_URL",
                "",
            ).strip()
        )

    if configured_endpoint:
        return configured_endpoint

    endpoint_env_vars = {
        "nvidia": (
            "NVIDIA_NIM_API_BASE",
            "NVIDIA_API_BASE",
        ),
        "groq": ("GROQ_API_BASE",),
        "openrouter": ("OPENROUTER_API_BASE",),
    }

    for env_name in endpoint_env_vars.get(provider, ()):
        endpoint = os.getenv(env_name, "").strip()

        if endpoint:
            return endpoint

    return ""


def _get_timeout_seconds(model, mode):
    """
    Get a model's timeout, capped at 10 seconds.

    A larger timeout in ModelRegistry.config cannot override this cap.
    """

    provider = _get_provider_name(model)
    config = _get_model_config(model)

    if provider == "gemini":
        default_timeout = (
            DEFAULT_GEMINI_THINK_TIMEOUT_SECONDS
            if mode == AIRequest.ModeChoices.THINK
            else DEFAULT_GEMINI_TIMEOUT_SECONDS
        )
    else:
        default_timeout = DEFAULT_TIMEOUT_SECONDS

    config_key = (
        "think_timeout_seconds"
        if mode == AIRequest.ModeChoices.THINK
        else "timeout_seconds"
    )

    configured_timeout = config.get(config_key)

    if (
        configured_timeout is None
        and mode == AIRequest.ModeChoices.THINK
    ):
        configured_timeout = config.get("timeout_seconds")

    if configured_timeout is None:
        return default_timeout

    if isinstance(configured_timeout, bool):
        return default_timeout

    try:
        timeout_seconds = int(configured_timeout)
    except (TypeError, ValueError, OverflowError):
        logger.warning(
            "Invalid model timeout configuration. provider=%s",
            provider,
        )
        return default_timeout

    return max(
        MIN_TIMEOUT_SECONDS,
        min(timeout_seconds, MAX_TIMEOUT_SECONDS),
    )


def _build_model_options(model):
    """Return only explicitly allowed inference options."""

    config = _get_model_config(model)

    options = {
        key: value
        for key, value in config.items()
        if key in ALLOWED_MODEL_OPTIONS
    }

    if "max_completion_tokens" in options:
        options.pop("max_tokens", None)

    return options


def _build_messages(message, mode):
    """Build system and user messages."""

    messages = [
        {
            "role": "system",
            "content": SYSTEM_PROMPT,
        }
    ]

    if mode == AIRequest.ModeChoices.THINK:
        messages.append(
            {
                "role": "system",
                "content": (
                    "Think mode is enabled. Carefully analyze the problem, "
                    "check relevant assumptions, and provide a well-"
                    "structured answer with useful explanations. Do not "
                    "output private internal chain-of-thought."
                ),
            }
        )

    messages.append(
        {
            "role": "user",
            "content": message,
        }
    )

    return messages


def _call_model(model, message, mode, web_search):
    """Call one registered AI model through LiteLLM."""

    if web_search:
        raise _configuration_error(
            model,
            "Web Search is not connected. Configure a real "
            "web-search integration before enabling it.",
        )

    _validate_model_availability(model)

    try:
        import litellm
    except ImportError as exc:
        raise _configuration_error(
            model,
            "LiteLLM is not installed. Install it using "
            "'python -m pip install litellm'.",
        ) from exc

    api_key = _get_provider_credentials(model)
    endpoint = _get_model_endpoint(model)
    litellm_model_name = _get_litellm_model_name(model)

    provider_name = _get_provider_name(model)
    is_self_hosted = _is_self_hosted_model(model)

    if is_self_hosted and not endpoint:
        raise _configuration_error(
            model,
            "The self-hosted model endpoint is not configured.",
        )

    timeout_seconds = _get_timeout_seconds(model, mode)

    completion_kwargs = {
        "model": litellm_model_name,
        "messages": _build_messages(message, mode),
        "api_key": api_key,
        "timeout": timeout_seconds,
        # Disable internal retries so failover is controlled here.
        "num_retries": 0,
        "stream": False,
        **_build_model_options(model),
    }

    if endpoint:
        completion_kwargs["api_base"] = endpoint

    # Optional provider-specific reasoning configuration.
    config = _get_model_config(model)
    reasoning_effort = config.get("reasoning_effort")

    if (
        provider_name == "gemini"
        and mode == AIRequest.ModeChoices.THINK
        and reasoning_effort in {"low", "medium", "high"}
    ):
        completion_kwargs["reasoning_effort"] = reasoning_effort

    try:
        response = litellm.completion(**completion_kwargs)

    except Exception as exc:
        error_name = type(exc).__name__

        # Do not log prompts, secrets, or raw provider response bodies.
        logger.warning(
            "AI provider call failed. provider=%s model=%s "
            "error_type=%s mode=%s timeout_seconds=%s",
            provider_name,
            litellm_model_name,
            error_name,
            mode,
            timeout_seconds,
        )

        # Failures are wrapped so the candidate loop can proceed to
        # the next eligible model, including after a timeout.
        raise AIServiceError(
            "The selected AI provider could not generate a response."
        ) from exc

    choices = _get_field(response, "choices")

    if not choices:
        raise AIServiceError(
            "The AI provider returned no response choices."
        )

    first_choice = choices[0]
    response_message = _get_field(first_choice, "message")
    content = _get_field(response_message, "content")
    answer = _extract_text(content)

    if not answer:
        raise AIServiceError(
            "The AI provider returned an empty response."
        )

    usage = _get_field(response, "usage")
    actual_model = _get_field(response, "model")

    return {
        "reply": answer,
        "provider": provider_name,
        "model": actual_model or model.model_id,
        "model_registry_id": model.pk,
        "web_search_used": False,
        "input_tokens": _get_usage_value(
            usage,
            "prompt_tokens",
            "input_tokens",
        ),
        "output_tokens": _get_usage_value(
            usage,
            "completion_tokens",
            "output_tokens",
        ),
    }


def _append_candidate(candidates, seen_ids, model):
    """Add an active registry model once, preserving candidate order."""

    if model is None:
        return

    if not getattr(model, "active", False):
        return

    model_id = getattr(model, "pk", None)

    if model_id is None:
        return

    if model_id in seen_ids:
        return

    seen_ids.add(model_id)
    candidates.append(model)


def _build_candidate_chain(message, mode, primary_model=None):
    """
    Build the model-attempt order.

    Order:
    1. Explicitly selected model, if supplied.
    2. Router's preferred model.
    3. Router's ranked fallback models.
    4. Other active registered models, ordered by priority and name.

    Unavailable models and models without credentials are skipped when
    attempted. They do not prevent trying a later model.
    """

    route = None
    candidates = []
    seen_ids = set()

    # Explicitly selected model must be attempted first.
    _append_candidate(
        candidates,
        seen_ids,
        primary_model,
    )

    try:
        route = choose_model(
            message,
            mode=mode,
            web_search=False,
            stream=False,
        )

    except NoSuitableModelError:
        # If routing has no suitable preferred model, still attempt
        # other active registry entries below.
        logger.warning(
            "Automatic router found no preferred model. "
            "Trying remaining active registry models."
        )

    if route is not None:
        _append_candidate(
            candidates,
            seen_ids,
            route.model,
        )

        for fallback_model in route.fallback_models:
            _append_candidate(
                candidates,
                seen_ids,
                fallback_model,
            )

    # Include remaining registered models so a failed preferred model
    # does not end the request while another active model is available.
    remaining_models = (
        ModelRegistry.objects.filter(active=True)
        .order_by("priority", "name")
    )

    for remaining_model in remaining_models:
        _append_candidate(
            candidates,
            seen_ids,
            remaining_model,
        )

    return route, candidates


def _log_failed_attempt(model, attempt_number, error):
    """Log safe metadata for a failed attempt before failover."""

    cause = getattr(error, "__cause__", None)
    underlying_error_name = (
        type(cause).__name__
        if cause is not None
        else type(error).__name__
    )

    logger.warning(
        "AI model attempt failed; trying next candidate. "
        "attempt=%s provider=%s model_id=%s error_type=%s",
        attempt_number,
        _get_provider_name(model),
        getattr(model, "model_id", "unknown"),
        underlying_error_name,
    )


def generate_reply(
    message,
    *,
    mode="auto",
    web_search=True,
    user=None,
    selected_model_id=None,
):
    """
    Generate a response with automatic per-model timeout failover.

    Every model call has a timeout capped at 10 seconds.
    When a model fails, times out, or is misconfigured, the next
    candidate is attempted.

    An explicitly selected model is always tried first. If it fails,
    other eligible models can provide a fallback response.

    Returned metadata identifies the model that actually succeeded.
    """

    if not isinstance(message, str) or not message.strip():
        raise ValueError("Message cannot be empty.")

    if not isinstance(mode, str):
        raise ValueError("Mode must be 'auto' or 'think'.")

    mode = mode.strip().lower()

    if mode not in {
        AIRequest.ModeChoices.AUTO,
        AIRequest.ModeChoices.THINK,
    }:
        raise ValueError("Mode must be 'auto' or 'think'.")

    if web_search:
        raise AIServiceConfigurationError(
            "Web Search integration is not available yet."
        )

    requested_model_id = None
    primary_model = None

    # Explicitly selected model: try it before any fallback.
    if selected_model_id is not None:
        try:
            requested_model_id = int(selected_model_id)
        except (TypeError, ValueError, OverflowError) as exc:
            raise AIServiceConfigurationError(
                "The selected model ID is invalid."
            ) from exc

        primary_model = ModelRegistry.objects.filter(
            pk=requested_model_id,
            active=True,
        ).first()

        if primary_model is None:
            raise AIServiceConfigurationError(
                "The selected model was not found or is not active."
            )

    route, candidates = _build_candidate_chain(
        message=message.strip(),
        mode=mode,
        primary_model=primary_model,
    )

    if not candidates:
        raise AIServiceError(
            "No active AI model is available for inference."
        )

    # Selected-model requests retain the requested mode.
    # Automatic requests use the router's resolved mode.
    if requested_model_id is None and route is not None:
        effective_mode = route.mode
        category = route.category
    else:
        effective_mode = mode
        category = (
            route.category
            if route is not None
            else AIRequest.TaskCategory.GENERAL
        )

    request_start = perf_counter()
    last_error = None

    for index, model in enumerate(candidates):
        attempt_number = index + 1

        try:
            result = _call_model(
                model=model,
                message=message.strip(),
                mode=effective_mode,
                web_search=False,
            )

            # The response must identify the model that actually
            # generated the answer, including when it is a fallback.
            result["category"] = category
            result["fallback_used"] = index > 0
            result["requested_model_registry_id"] = requested_model_id
            result["fallback_from_registry_id"] = (
                candidates[0].pk
                if index > 0
                else None
            )

            result["response_time_ms"] = max(
                0,
                int((perf_counter() - request_start) * 1000),
            )

            if index > 0:
                logger.info(
                    "AI fallback succeeded. requested_model_id=%s "
                    "actual_model_id=%s provider=%s attempts=%s",
                    requested_model_id,
                    result.get("model_registry_id"),
                    result.get("provider"),
                    attempt_number,
                )

            return result

        except (AIServiceConfigurationError, AIServiceError) as exc:
            # A missing credential, unavailable model, provider error,
            # or timeout must not stop the fallback chain.
            last_error = exc

            _log_failed_attempt(
                model,
                attempt_number,
                exc,
            )

            continue

        except Exception as exc:
            last_error = exc

            _log_failed_attempt(
                model,
                attempt_number,
                exc,
            )

            continue

    # All candidate attempts failed or timed out.
    logger.error(
        "All AI model attempts failed. candidate_count=%s "
        "requested_model_id=%s",
        len(candidates),
        requested_model_id,
    )

    raise AIServiceError(
        "All eligible AI models failed or timed out. "
        "Please try again shortly."
    ) from last_error