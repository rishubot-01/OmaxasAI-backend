"""
Base provider interface for OmaxasAI.

Every AI provider adapter follows this contract so the application
can work with external APIs and self-hosted models without depending
on provider-specific response formats.

Provider credentials must remain in environment variables.
Monetary cost is deliberately excluded.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, TYPE_CHECKING


if TYPE_CHECKING:
    from ..models import ModelRegistry


class ProviderError(RuntimeError):
    """Base exception for AI provider failures."""


class ProviderConfigurationError(ProviderError):
    """Raised when a provider is incorrectly configured."""


class ProviderUnavailableError(ProviderError):
    """Raised when a provider is temporarily unavailable."""


class ProviderResponseError(ProviderError):
    """Raised when a provider returns an invalid response."""


@dataclass(frozen=True)
class ProviderResult:
    """
    Normalized result returned by a provider adapter.

    Attributes:
        text: Generated response text.
        provider: Normalized provider name.
        model: Actual or reported model identifier.
        input_tokens: Input token count, if available.
        output_tokens: Output token count, if available.
        response_time_ms: Provider-call duration in milliseconds.
        raw_status: Safe operational status, not a raw provider response.

    Monetary cost and API credentials are deliberately excluded.
    """

    text: str
    provider: str
    model: str
    input_tokens: int | None = None
    output_tokens: int | None = None
    response_time_ms: int | None = None
    raw_status: str | None = None


class BaseAIProvider(ABC):
    """
    Abstract interface for OmaxasAI provider adapters.

    Implementations may connect to external AI APIs or to
    OpenAI-compatible endpoints hosting self-hosted models.

    An adapter should implement supports() and generate().
    """

    @abstractmethod
    def supports(self, model: ModelRegistry) -> bool:
        """
        Return whether this adapter can serve the registered model.

        This check should validate adapter/backend compatibility.
        API credentials and actual provider availability must also
        be checked before inference.
        """
        raise NotImplementedError

    @abstractmethod
    def generate(
        self,
        *,
        model: ModelRegistry,
        messages: list[dict[str, str]],
        stream: bool = False,
        timeout: int = 60,
        options: dict[str, Any] | None = None,
    ) -> ProviderResult:
        """
        Generate a response using the specified registered model.

        Args:
            model: Registered model configuration.
            messages: Normalized role/content messages.
            stream: Whether the adapter should request upstream streaming.
                The adapter may reject this option if unsupported.
            timeout: Maximum time allowed for the provider request.
            options: Explicitly allowed, non-secret generation parameters.

        Returns:
            A normalized ProviderResult.

        Raises:
            ProviderConfigurationError:
                Required credentials, model configuration, or settings
                are missing or invalid.
            ProviderUnavailableError:
                The provider is temporarily unavailable.
            ProviderResponseError:
                The provider response is missing or invalid.
            ProviderError:
                Another provider-related failure occurred.

        Note:
            ProviderResult represents a completed response. This
            interface alone does not deliver individual text chunks
            to the frontend. Client-visible SSE streaming requires
            a separate streaming contract and HTTP response handler.
        """
        raise NotImplementedError