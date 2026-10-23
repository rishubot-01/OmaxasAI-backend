"""
OmaxasAI AI service.

Routes prompts to registered AI models through LiteLLM.
Supports automatic routing and explicitly selected registry models.

Provider credentials are read from environment variables.
This service does not track monetary cost.
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


# Standard provider credential names.
# ModelRegistry.credential_env_var can override these defaults.
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


# Backward-compatible aliases for provider credentials.
#
# The environment variable names are checked in this order:
# 1. ModelRegistry.credential_env_var
# 2. Standard provider variable
# 3. Router provider variable
# 4. Provider aliases
#
# Only environment-variable NAMES appear in logs.
# Secret values are never logged.
PROVIDER_ENV_ALIASES = {
    "gemini": (
        "GEMINI_API_KEY",
        "GOOGLE_API_KEY",
    ),
    "nvidia": (
        "NVIDIA_NIM_API_KEY",
        "NVIDIA_API_KEY",
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


MIN_TIMEOUT_SECONDS = 5
MAX_TIMEOUT_SECONDS = 180

DEFAULT_TIMEOUT_SECONDS = 60
DEFAULT_GEMINI_TIMEOUT_SECONDS = 90
DEFAULT_GEMINI_THINK_TIMEOUT_SECONDS = 120


def _get_field(value, field_name, default=None):
    """Read a value from a dictionary or an object."""

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

    return (
        provider.strip().lower()
        if isinstance(provider, str)
        else ""
    )


def _get_usage_value(usage, *field_names):
    """Extract token counts from dictionaries or response objects."""

    if usage is None:
        return None

    for field_name in field_names:
        value = _get_field(usage, field_name)

        if value is None:
            continue

        try:
            count = int(value)
        except (TypeError, ValueError, OverflowError):
            continue

        if count >= 0:
            return count

    return None


def _extract_text(content):
    """Convert supported model response formats into plain text."""

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
    """
    Log safe configuration diagnostics and create a configuration error.

    Does not log prompts, API key values, or raw provider responses.
    """

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
    """
    Resolve provider API credentials from server environment variables.

    NVIDIA supports both NVIDIA_NIM_API_KEY and NVIDIA_API_KEY.
    Gemini supports GEMINI_API_KEY and GOOGLE_API_KEY.

    A model-specific credential variable is preferred, but a missing
    variable falls back to the provider's standard aliases.
    """

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
            api_key = os.getenv(
                configured_env_var,
                "",
            ).strip()

            if not api_key:
                raise _configuration_error(
                    model,
                    "The configured self-hosted model credential is missing.",
                )

            return api_key

        # Retain support for local OpenAI-compatible endpoints.
        return "EMPTY"

    if not candidate_names:
        raise _configuration_error(
            model,
            "No credential environment variable is configured "
            "for this provider.",
        )

    for env_name in candidate_names:
        api_key = os.getenv(env_name, "").strip()

        if api_key:
            return api_key

    # Show checked variable NAMES, never their values.
    raise _configuration_error(
        model,
        "The provider credential is missing. Checked environment "
        "variable names: " + ", ".join(candidate_names),
    )


def _get_litellm_model_name(model):
    """
    Resolve ModelRegistry.model_id to a LiteLLM model identifier.

    config["litellm_model"] takes precedence and should contain a
    complete LiteLLM identifier suitable for the registered provider.
    """

    config = _get_model_config(model)

    configured_model = config.get("litellm_model")

    if (
        isinstance(configured_model, str)
        and configured_model.strip()
    ):
        return configured_model.strip()

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
    prefix = LITELLM_PROVIDER_PREFIXES.get(provider)

    if prefix is None:
        return model_id

    if provider == "openai":
        return model_id

    # Do not add the provider prefix a second time.
    if prefix and model_id.startswith(prefix):
        return model_id

    return f"{prefix}{model_id}"


def _get_model_endpoint(model):
    """Resolve an optional provider or self-hosted API endpoint."""

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
    """Return a bounded timeout, optionally configured per model."""

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
    """Return only permitted inference options."""

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
        "num_retries": 0,
        "stream": False,
        **_build_model_options(model),
    }

    if endpoint:
        completion_kwargs["api_base"] = endpoint

    # Apply reasoning options only when explicitly configured.
    #
    # This avoids sending a provider-specific parameter to every
    # Gemini model based solely on a hardcoded model-name substring.
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
        logger.warning(
            "AI provider call failed. provider=%s model=%s "
            "error_type=%s mode=%s timeout_seconds=%s",
            provider_name,
            litellm_model_name,
            type(exc).__name__,
            mode,
            timeout_seconds,
        )

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


def generate_reply(
    message,
    *,
    mode="auto",
    web_search=False,
    user=None,
    selected_model_id=None,
):
    """
    Generate a response through a selected or automatically routed model.

    An explicitly selected model is called directly without automatic
    routing or fallback to another provider.

    Automatic mode uses the router and its configured fallback models.
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

    # ---------------------------------------------------------
    # Path 1: Explicit model selection
    # ---------------------------------------------------------
    # Skip model_router and quality scoring. This avoids unnecessary
    # routing work when the frontend has selected a specific model.
    # ---------------------------------------------------------

    if selected_model_id is not None:
        try:
            selected_model_id = int(selected_model_id)
        except (TypeError, ValueError, OverflowError) as exc:
            raise AIServiceConfigurationError(
                "The selected model ID is invalid."
            ) from exc

        selected_model = ModelRegistry.objects.filter(
            pk=selected_model_id,
            active=True,
        ).first()

        if selected_model is None:
            raise AIServiceConfigurationError(
                "The selected model was not found or is not active."
            )

        _validate_model_availability(selected_model)

        start_time = perf_counter()

        result = _call_model(
            model=selected_model,
            message=message.strip(),
            mode=mode,
            web_search=False,
        )

        result["category"] = AIRequest.TaskCategory.GENERAL
        result["fallback_used"] = False
        result["response_time_ms"] = max(
            0,
            int((perf_counter() - start_time) * 1000),
        )

        return result

    # ---------------------------------------------------------
    # Path 2: Automatic routing
    # ---------------------------------------------------------

    try:
        route = choose_model(
            message,
            mode=mode,
            web_search=web_search,
            stream=False,
        )

    except NoSuitableModelError as exc:
        raise AIServiceError(
            "No suitable AI model is configured or available."
        ) from exc

    candidates = (route.model, *route.fallback_models)

    effective_mode = route.mode
    category = route.category
    effective_web_search = route.web_search

    start_time = perf_counter()
    last_error = None

    for index, model in enumerate(candidates):
        try:
            result = _call_model(
                model=model,
                message=message.strip(),
                mode=effective_mode,
                web_search=effective_web_search,
            )

            result["category"] = category
            result["fallback_used"] = index > 0
            result["response_time_ms"] = max(
                0,
                int((perf_counter() - start_time) * 1000),
            )

            return result

        except AIServiceConfigurationError:
            # Configuration errors should remain explicit. Do not
            # hide missing credentials or an invalid endpoint.
            raise

        except AIServiceError as exc:
            last_error = exc

            logger.warning(
                "AI model attempt failed. provider=%s model=%s",
                _get_provider_name(model),
                getattr(model, "model_id", "unknown"),
            )

        except Exception as exc:
            last_error = exc

            logger.warning(
                "Unexpected AI model failure. provider=%s "
                "error_type=%s",
                _get_provider_name(model),
                type(exc).__name__,
            )

    raise AIServiceError(
        "All eligible AI model attempts failed."
    ) from last_error