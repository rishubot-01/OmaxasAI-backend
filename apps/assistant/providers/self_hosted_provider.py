"""
Self-hosted AI provider for OmaxasAI.

Connects to an OpenAI-compatible inference endpoint, such as
a vLLM server deployed on a RunPod GPU machine.

The endpoint and credentials must be configured by the server
operator. They must never come from a user's chat message.

Provider credentials remain in environment variables.
Monetary cost is deliberately not tracked.
"""

import logging
import os
from time import perf_counter
from typing import Any
from urllib.parse import urlsplit

from .base import (
    BaseAIProvider,
    ProviderConfigurationError,
    ProviderError,
    ProviderResponseError,
    ProviderUnavailableError,
    ProviderResult,
)


logger = logging.getLogger(__name__)


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


MIN_TIMEOUT_SECONDS = 1
MAX_TIMEOUT_SECONDS = 300


def _get_value(obj: Any, key: str, default=None):
    """Read a field from a dictionary or response object."""

    if isinstance(obj, dict):
        return obj.get(key, default)

    return getattr(obj, key, default)


def _safe_non_negative_int(value) -> int | None:
    """Normalize optional token counts."""

    if value is None or isinstance(value, bool):
        return None

    try:
        number = int(value)
    except (TypeError, ValueError, OverflowError):
        return None

    return number if number >= 0 else None


def _extract_text(content) -> str:
    """Extract readable text from common chat-completion formats."""

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


class SelfHostedProvider(BaseAIProvider):
    """
    Provider adapter for OmaxasAI-managed inference servers.

    Expects an OpenAI-compatible chat-completions API, such as
    a vLLM server deployed on a configured inference endpoint.

    A native RunPod Serverless endpoint may require a separate
    adapter if it does not implement the OpenAI-compatible API.
    """

    def supports(self, model) -> bool:
        """Check whether the registry entry uses the self-hosted backend."""

        backend_type = str(
            getattr(model, "backend_type", "") or ""
        ).strip().lower()

        return backend_type == "self_hosted"

    def _resolve_endpoint(self, model) -> str:
        """
        Resolve and validate the trusted inference endpoint.

        Priority:
        1. ModelRegistry.endpoint_url
        2. SELF_HOSTED_MODEL_BASE_URL
        3. OMAXASAI_SELF_HOSTED_BASE_URL
        """

        configured_endpoint = str(
            getattr(model, "endpoint_url", "") or ""
        ).strip()

        endpoint = (
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

        if not endpoint:
            raise ProviderConfigurationError(
                "The self-hosted inference endpoint is not configured."
            )

        try:
            parsed = urlsplit(endpoint)
            hostname = parsed.hostname
            port = parsed.port
        except ValueError as exc:
            raise ProviderConfigurationError(
                "The self-hosted endpoint URL is invalid."
            ) from exc

        if (
            parsed.scheme.lower() not in {"https", "http"}
            or not hostname
        ):
            raise ProviderConfigurationError(
                "The self-hosted endpoint must be a valid "
                "HTTP or HTTPS URL."
            )

        if parsed.username or parsed.password or parsed.fragment:
            raise ProviderConfigurationError(
                "Endpoint URLs must not contain credentials or fragments."
            )

        if port is not None and not 1 <= port <= 65535:
            raise ProviderConfigurationError(
                "The self-hosted endpoint port is invalid."
            )

        # Permit plain HTTP only for local development.
        local_hosts = {
            "localhost",
            "127.0.0.1",
            "::1",
        }

        if (
            parsed.scheme.lower() == "http"
            and hostname.lower() not in local_hosts
        ):
            raise ProviderConfigurationError(
                "Remote self-hosted endpoints must use HTTPS."
            )

        return endpoint.rstrip("/")

    def _resolve_api_key(self, model) -> str:
        """
        Load the inference API key from the environment.

        ModelRegistry stores the environment-variable name only.

        No-auth mode must be explicitly enabled by the server operator.
        """

        env_name = (
            str(
                getattr(model, "credential_env_var", "") or ""
            ).strip()
            or "OMAXASAI_SELF_HOSTED_API_KEY"
        )

        api_key = os.getenv(env_name, "").strip()

        if api_key:
            return api_key

        allow_no_auth = os.getenv(
            "OMAXASAI_SELF_HOSTED_ALLOW_NO_AUTH",
            "false",
        ).strip().lower() in {
            "true",
            "1",
            "yes",
            "on",
        }

        if allow_no_auth:
            return "EMPTY"

        raise ProviderConfigurationError(
            "The self-hosted model API key is not configured. "
            "Configure the required backend environment variable."
        )

    def _resolve_model_id(self, model) -> str:
        """
        Resolve the identifier expected by LiteLLM.

        config["litellm_model"] takes precedence over model_id.
        Otherwise, use the LiteLLM OpenAI-compatible provider prefix.
        """

        config = getattr(model, "config", {})

        if not isinstance(config, dict):
            config = {}

        configured_id = config.get("litellm_model")

        if (
            isinstance(configured_id, str)
            and configured_id.strip()
        ):
            return configured_id.strip()

        served_model_id = str(
            getattr(model, "model_id", "") or ""
        ).strip()

        if not served_model_id:
            raise ProviderConfigurationError(
                "The self-hosted model identifier is missing."
            )

        # Do not add the openai/ prefix twice.
        if served_model_id.startswith("openai/"):
            return served_model_id

        # LiteLLM uses openai/<served-model-id> when calling
        # OpenAI-compatible self-hosted inference endpoints.
        return f"openai/{served_model_id}"

    def _resolve_options(
        self,
        model,
        options: dict[str, Any] | None,
    ) -> dict[str, Any]:
        """Return only approved, non-secret inference options."""

        config = getattr(model, "config", {})

        if not isinstance(config, dict):
            config = {}

        safe_options = {
            key: value
            for key, value in config.items()
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

        # Avoid sending conflicting token-limit parameters.
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
        """Generate a completed response from a self-hosted model."""

        if not self.supports(model):
            raise ProviderConfigurationError(
                "SelfHostedProvider cannot serve this model backend."
            )

        if stream:
            raise ProviderConfigurationError(
                "Streaming is not implemented in this provider adapter yet."
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

        if not MIN_TIMEOUT_SECONDS <= timeout <= MAX_TIMEOUT_SECONDS:
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

        endpoint = self._resolve_endpoint(model)
        api_key = self._resolve_api_key(model)
        model_id = self._resolve_model_id(model)
        safe_options = self._resolve_options(model, options)

        request_started = perf_counter()

        try:
            response = litellm.completion(
                model=model_id,
                messages=messages,
                api_base=endpoint,
                api_key=api_key,
                timeout=timeout,
                num_retries=0,
                stream=False,
                **safe_options,
            )

        except Exception as exc:
            error_name = type(exc).__name__

            # Do not log prompts, keys, or raw provider responses.
            logger.warning(
                "Self-hosted AI request failed. "
                "model=%s error_type=%s timeout=%s",
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
                    "The self-hosted server rejected the request "
                    "or its configuration."
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
                    "The self-hosted model server is temporarily unavailable."
                ) from exc

            raise ProviderError(
                "The self-hosted model request failed."
            ) from exc

        choices = _get_value(response, "choices", [])

        if not choices:
            raise ProviderResponseError(
                "The self-hosted model returned no response choices."
            )

        choice = choices[0]
        response_message = _get_value(choice, "message")

        answer = _extract_text(
            _get_value(response_message, "content")
        )

        if not answer:
            raise ProviderResponseError(
                "The self-hosted model returned an empty text response."
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

        response_time_ms = max(
            0,
            int((perf_counter() - request_started) * 1000),
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
            provider="omaxas",
            model=returned_model.strip(),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            response_time_ms=response_time_ms,
            raw_status="completed",
        )