"""
LiteLLM provider adapter for OmaxasAI.

Connects registered external AI models through LiteLLM and
normalizes their responses using the common provider interface.

Actual provider credentials must remain in environment variables.
Monetary cost is deliberately not tracked.
"""

import logging
import os
from time import perf_counter
from typing import Any

from .base import (
    BaseAIProvider,
    ProviderConfigurationError,
    ProviderError,
    ProviderResponseError,
    ProviderUnavailableError,
    ProviderResult,
)


logger = logging.getLogger(__name__)


# Keep credential names consistent with ai_service.py and model_router.py.
# ModelRegistry.credential_env_var can override the provider default.
SUPPORTED_PROVIDERS = {
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


# Only explicitly permitted inference parameters.
ALLOWED_OPTIONS = {
    "temperature",
    "max_tokens",
    "max_completion_tokens",
    "top_p",
    "frequency_penalty",
    "presence_penalty",
    "seed",
}


def _get_value(obj: Any, key: str, default=None):
    """Read a field from a dictionary or an object."""

    if isinstance(obj, dict):
        return obj.get(key, default)

    return getattr(obj, key, default)


def _safe_non_negative_int(value) -> int | None:
    """Normalize an optional non-negative integer."""

    if value is None or isinstance(value, bool):
        return None

    try:
        number = int(value)
    except (TypeError, ValueError, OverflowError):
        return None

    return number if number >= 0 else None


def _extract_content(content) -> str:
    """Extract readable text from common chat response formats."""

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

        item_type = _get_value(item, "type")

        if item_type not in (None, "text", "output_text"):
            continue

        text_value = _get_value(item, "text")

        if isinstance(text_value, str) and text_value.strip():
            parts.append(text_value.strip())

    return "\n".join(parts).strip()


class LiteLLMProvider(BaseAIProvider):
    """
    Provider adapter for registered external AI models.

    ModelRegistry.model_id should contain a valid LiteLLM model
    identifier. config["litellm_model"] overrides model_id.

    OpenRouter model IDs should use the identifier expected by
    LiteLLM, for example:

        openrouter/provider/model-name

    The exact identifier depends on the upstream model.
    """

    def supports(self, model) -> bool:
        """Return whether this adapter supports the registry entry."""

        provider = str(
            getattr(model, "provider", "")
        ).strip().lower()

        backend_type = getattr(model, "backend_type", "")

        return (
            backend_type == "external_api"
            and provider in SUPPORTED_PROVIDERS
        )

    def _resolve_api_key(self, model) -> str:
        """
        Resolve credentials from environment variables only.

        An explicitly configured variable is checked first.
        If it is empty, the standard provider variable is checked
        as a fallback, consistent with ai_service.py.
        """

        provider = str(
            getattr(model, "provider", "")
        ).strip().lower()

        configured_env_var = str(
            getattr(model, "credential_env_var", "") or ""
        ).strip()

        standard_env_var = SUPPORTED_PROVIDERS.get(
            provider,
            "",
        )

        candidate_names = []

        for env_name in (
            configured_env_var,
            standard_env_var,
        ):
            if env_name and env_name not in candidate_names:
                candidate_names.append(env_name)

        if not candidate_names:
            raise ProviderConfigurationError(
                "No credential environment variable is configured "
                "for the selected provider."
            )

        for env_name in candidate_names:
            api_key = os.getenv(env_name, "").strip()

            if api_key:
                return api_key

        raise ProviderConfigurationError(
            "The selected AI provider credential is missing "
            "from the server environment. Configure one of: "
            + ", ".join(candidate_names)
        )

    def _resolve_model_id(self, model) -> str:
        """
        Resolve the exact LiteLLM model identifier.

        config["litellm_model"] takes precedence over model_id.
        Provider prefixes are not guessed or automatically rewritten.
        """

        config = getattr(model, "config", {})

        if not isinstance(config, dict):
            config = {}

        configured_model = config.get("litellm_model")

        if (
            isinstance(configured_model, str)
            and configured_model.strip()
        ):
            model_id = configured_model.strip()
        else:
            model_id = str(
                getattr(model, "model_id", "") or ""
            ).strip()

        if not model_id:
            raise ProviderConfigurationError(
                "The registered model has no LiteLLM model identifier."
            )

        return model_id

    def _resolve_endpoint(self, model) -> str:
        """
        Resolve an optional provider API endpoint.

        ModelRegistry.endpoint_url takes precedence over the
        provider-specific environment configuration.
        """

        configured_endpoint = str(
            getattr(model, "endpoint_url", "") or ""
        ).strip()

        if configured_endpoint:
            return configured_endpoint

        provider = str(
            getattr(model, "provider", "")
        ).strip().lower()

        endpoint_environment_variables = {
            "groq": ("GROQ_API_BASE",),
            "openrouter": ("OPENROUTER_API_BASE",),
            "nvidia": (
                "NVIDIA_NIM_API_BASE",
                "NVIDIA_API_BASE",
            ),
        }

        for env_name in endpoint_environment_variables.get(
            provider,
            (),
        ):
            endpoint = os.getenv(env_name, "").strip()

            if endpoint:
                return endpoint

        return ""

    def _resolve_options(
        self,
        model,
        options: dict[str, Any] | None,
    ) -> dict[str, Any]:
        """Merge explicitly allowed non-secret inference options."""

        registry_config = getattr(model, "config", {})

        if not isinstance(registry_config, dict):
            registry_config = {}

        safe_options = {
            key: value
            for key, value in registry_config.items()
            if key in ALLOWED_OPTIONS
        }

        if options is not None:
            if not isinstance(options, dict):
                raise ProviderConfigurationError(
                    "Inference options must be a dictionary."
                )

            safe_options.update({
                key: value
                for key, value in options.items()
                if key in ALLOWED_OPTIONS
            })

        # Avoid sending conflicting output-token-limit parameters.
        if "max_completion_tokens" in safe_options:
            safe_options.pop("max_tokens", None)

        return safe_options

    def generate(
        self,
        *,
        model,
        messages: list[dict[str, str]],
        stream: bool = False,
        timeout: int = 60,
        options: dict[str, Any] | None = None,
    ) -> ProviderResult:
        """
        Generate a completed response using a registered external model.

        This adapter returns a completed ProviderResult. True token
        streaming requires a compatible streaming interface and caller.
        """

        if not self.supports(model):
            raise ProviderConfigurationError(
                "LiteLLMProvider cannot serve this model backend."
            )

        if stream:
            raise ProviderConfigurationError(
                "Streaming is not implemented in this provider interface yet."
            )

        if (
            not isinstance(messages, list)
            or not messages
            or any(not isinstance(item, dict) for item in messages)
        ):
            raise ProviderResponseError(
                "A non-empty list of chat messages is required."
            )

        if isinstance(timeout, bool) or not isinstance(timeout, int):
            raise ProviderConfigurationError(
                "Timeout must be an integer."
            )

        if timeout < 1 or timeout > 300:
            raise ProviderConfigurationError(
                "Timeout must be between 1 and 300 seconds."
            )

        try:
            import litellm
        except ImportError as exc:
            raise ProviderConfigurationError(
                "LiteLLM is not installed. Run "
                "'python -m pip install litellm'."
            ) from exc

        provider_name = str(
            getattr(model, "provider", "")
        ).strip().lower()

        api_key = self._resolve_api_key(model)
        model_id = self._resolve_model_id(model)
        endpoint = self._resolve_endpoint(model)
        safe_options = self._resolve_options(model, options)

        call_kwargs = {
            "model": model_id,
            "messages": messages,
            "api_key": api_key,
            "timeout": timeout,
            "num_retries": 0,
            "stream": False,
            **safe_options,
        }

        if endpoint:
            call_kwargs["api_base"] = endpoint

        start = perf_counter()

        try:
            response = litellm.completion(**call_kwargs)

        except Exception as exc:
            # Log only safe operational metadata.
            # Never log prompts, provider response bodies, or API keys.
            error_name = type(exc).__name__

            logger.warning(
                "External AI call failed. provider=%s model=%s "
                "error_type=%s timeout=%s",
                provider_name,
                model_id,
                error_name,
                timeout,
            )

            if error_name in {
                "AuthenticationError",
                "PermissionDeniedError",
                "BadRequestError",
                "NotFoundError",
                "UnsupportedParamsError",
            }:
                raise ProviderConfigurationError(
                    "The AI provider rejected the request or its configuration."
                ) from exc

            if error_name in {
                "RateLimitError",
                "ServiceUnavailableError",
                "Timeout",
                "TimeoutError",
                "APIConnectionError",
                "InternalServerError",
            }:
                raise ProviderUnavailableError(
                    "The AI provider is temporarily unavailable."
                ) from exc

            raise ProviderError(
                "The external AI provider request failed."
            ) from exc

        choices = _get_value(response, "choices", [])

        if not choices:
            raise ProviderResponseError(
                "The AI provider returned no response choices."
            )

        first_choice = choices[0]
        response_message = _get_value(first_choice, "message")
        content = _get_value(response_message, "content")
        answer = _extract_content(content)

        if not answer:
            raise ProviderResponseError(
                "The AI provider returned an empty text response."
            )

        usage = _get_value(response, "usage")

        input_tokens = _safe_non_negative_int(
            _get_value(usage, "prompt_tokens")
        )

        if input_tokens is None:
            input_tokens = _safe_non_negative_int(
                _get_value(usage, "input_tokens")
            )

        output_tokens = _safe_non_negative_int(
            _get_value(usage, "completion_tokens")
        )

        if output_tokens is None:
            output_tokens = _safe_non_negative_int(
                _get_value(usage, "output_tokens")
            )

        elapsed_ms = max(
            0,
            int((perf_counter() - start) * 1000),
        )

        returned_model = _get_value(
            response,
            "model",
            model_id,
        )

        if (
            not isinstance(returned_model, str)
            or not returned_model.strip()
        ):
            returned_model = model_id

        return ProviderResult(
            text=answer,
            provider=provider_name,
            model=returned_model.strip(),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            response_time_ms=elapsed_ms,
            raw_status="completed",
        )