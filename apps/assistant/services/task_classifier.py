"""
Task classification for OmaxasAI.

Identifies the primary category of a user request.
This module does not call external AI providers.
"""

import re
from typing import Final


# Explicit coding intent. Merely mentioning Python, an API,
# or a function does not automatically make a question coding.
CODING_PATTERNS: Final[tuple[str, ...]] = (
    r"\b(code likho|write code|generate code|source code|"
    r"code snippet|coding task|coding problem)\b",
    r"\b(debug|debugging|debugger|traceback|stack trace|"
    r"syntax error|compiler error|runtime error)\b",
    r"\b(fix|solve|debug)\b.{0,60}\b(bug|error|exception|"
    r"traceback|code|script|function|program)\b",
    r"\b(build|create|write|implement|refactor|review|"
    r"test|optimize|optimise|run|execute|fix)\b"
    r".{0,80}\b(code|program|function|class|script|"
    r"api endpoint|sql query|algorithm|component)\b",
    r"\b(python|javascript|typescript|django|react|sql|"
    r"html|css|api endpoint)\b.{0,80}\b(code|script|"
    r"function|class|program|implementation|query|"
    r"component|debug|bug fix)\b",
    r"\b(code|program|function|class|script|sql query|"
    r"api endpoint)\b.{0,60}\b(error|bug|debug|"
    r"implement|refactor|fix|write|create)\b",
    r"\bhow to (program|code|debug|implement|deploy)\b",
    r"\bhow do i (write|run|debug|test|build|"
    r"implement|execute)\b.{0,80}\b(code|program|"
    r"python|javascript|api|function|script)\b",
    r"\b(code|coding|programming|debug|debugging|"
    r"bug fix|stack trace|traceback)\b",
)


RESEARCH_PATTERNS: Final[tuple[str, ...]] = (
    r"\b(research|latest|current|recent|news|sources|"
    r"citations|references|web search|market research|"
    r"compare|comparison|statistics|report|trends)\b",
    r"\b(today|right now|this year|updated information)\b",
    r"\blatest news\b",
    r"\bsearch the web\b",
    r"\bki latest jankari\b",
)


WRITING_PATTERNS: Final[tuple[str, ...]] = (
    r"\b(rewrite|proofread|draft|essay|article|blog|story|"
    r"caption|email|letter|summarize|summarise|translate|"
    r"grammar|paraphrase)\b",
    r"\bwrite\b.{0,40}\b(email|letter|essay|article|"
    r"blog|story|caption|paragraph)\b",
    r"\bmake this professional\b",
    r"\bimprove this text\b",
)


REASONING_PATTERNS: Final[tuple[str, ...]] = (
    r"\b(reasoning|logic puzzle|mathematical proof|"
    r"prove that|deduce|derive|multi-step problem|"
    r"step by step|critical thinking)\b",
    r"\bsolve this equation\b",
    r"\bcomplex maths\b",
    r"\blogic problem\b",
)


VALID_CATEGORIES: Final[frozenset[str]] = frozenset({
    "general",
    "coding",
    "research",
    "reasoning",
    "writing",
    "vision",
    "other",
})


def _matches_any(text: str, patterns: tuple[str, ...]) -> bool:
    """Return True if any intent pattern matches the text."""

    return any(
        re.search(pattern, text, flags=re.IGNORECASE)
        for pattern in patterns
    )


def classify_task(
    message: str,
    *,
    has_images: bool = False,
    web_search: bool = False,
) -> str:
    """
    Return the primary category of a user request.

    Possible categories:
    coding, research, reasoning, writing,
    vision, general, other.

    Think mode is handled separately by the model router.
    """

    if not isinstance(message, str):
        return "other"

    text = message.strip().lower()

    if has_images:
        return "vision"

    if not text:
        return "other"

    # An explicitly enabled web-search workflow is research.
    if web_search:
        return "research"

    # Explicit software-development intent takes priority over
    # generic mentions of technology or programming languages.
    if _matches_any(text, CODING_PATTERNS):
        return "coding"

    if _matches_any(text, RESEARCH_PATTERNS):
        return "research"

    if _matches_any(text, WRITING_PATTERNS):
        return "writing"

    if _matches_any(text, REASONING_PATTERNS):
        return "reasoning"

    return "general"


def is_valid_category(category: str) -> bool:
    """Check whether a category is supported by OmaxasAI."""

    return category in VALID_CATEGORIES