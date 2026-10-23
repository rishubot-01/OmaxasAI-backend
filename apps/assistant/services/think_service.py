
"""
Think mode service for OmaxasAI.

Think mode prioritizes models registered with reasoning
capabilities. It returns a useful answer and explanation,
not a private internal reasoning transcript.
"""

from .ai_service import (
    AIServiceError,
    generate_reply,
)


class ThinkModeError(ValueError):
    """Raised when Think mode receives invalid input."""


def generate_think_reply(message: str, *, user=None) -> dict:
    """
    Generate an answer using OmaxasAI Think mode.

    The model router will prioritize registered models
    with the 'reasoning' or 'think' capability.

    Args:
        message: The user's question or problem.
        user: Optional authenticated user for future routing policies.

    Returns:
        A dictionary containing the answer and model metadata.

    Raises:
        ThinkModeError: If the prompt is empty or invalid.
        AIServiceError: If model selection or generation fails.
    """

    if not isinstance(message, str):
        raise ThinkModeError("Message must be text.")

    message = message.strip()

    if not message:
        raise ThinkModeError("Message cannot be empty.")

    result = generate_reply(
        message,
        mode="think",
        web_search=False,
        user=user,
    )

    # Ensure the caller can identify the response mode.
    result["mode"] = "think"

    return result

