import uuid

from django.conf import settings
from django.db import models


COMING_SOON_STATUSES = {
    "coming soon",
    "coming_soon",
    "not_available",
}


class ModelRegistry(models.Model):
    """
    Registry of external AI models and future OmaxasAI
    self-hosted models.

    Never store actual API keys in this table.
    Provider availability is not determined by provider name.
    """

    class ProviderChoices(models.TextChoices):
        OPENAI = "openai", "OpenAI"
        GEMINI = "gemini", "Google Gemini"
        ANTHROPIC = "anthropic", "Anthropic"
        XAI = "xai", "xAI"
        DEEPSEEK = "deepseek", "DeepSeek"
        MISTRAL = "mistral", "Mistral"
        COHERE = "cohere", "Cohere"
        GROQ = "groq", "Groq"
        OPENROUTER = "openrouter", "OpenRouter"
        TOGETHER = "together", "Together AI"
        FIREWORKS = "fireworks", "Fireworks AI"
        CEREBRAS = "cerebras", "Cerebras"
        PERPLEXITY = "perplexity", "Perplexity"
        HUGGINGFACE = "huggingface", "Hugging Face"
        NVIDIA = "nvidia", "NVIDIA"
        OMAXAS = "omaxas", "OmaxasAI"
        CUSTOM = "custom", "Custom Provider"

    class BackendType(models.TextChoices):
        EXTERNAL_API = "external_api", "External API"
        SELF_HOSTED = "self_hosted", "Self-hosted Model"

    name = models.CharField(max_length=120)

    provider = models.CharField(
        max_length=30,
        choices=ProviderChoices.choices,
    )

    # Actual upstream model ID for this provider.
    model_id = models.CharField(max_length=255)

    backend_type = models.CharField(
        max_length=20,
        choices=BackendType.choices,
        default=BackendType.EXTERNAL_API,
    )

    endpoint_url = models.URLField(
        max_length=500,
        blank=True,
    )

    # Environment-variable name only, never the secret key.
    credential_env_var = models.CharField(
        max_length=100,
        blank=True,
    )

    # Example: ["chat", "general", "coding", "reasoning"]
    capabilities = models.JSONField(
        default=list,
        blank=True,
    )

    # Non-secret provider configuration.
    #
    # Available:
    # {"status": "available", "litellm_model": "groq/your-model-id"}
    #
    # Coming Soon:
    # {"status": "coming_soon"}
    config = models.JSONField(
        default=dict,
        blank=True,
    )

    context_window = models.PositiveIntegerField(
        null=True,
        blank=True,
    )

    supports_streaming = models.BooleanField(default=True)
    supports_vision = models.BooleanField(default=False)
    supports_tools = models.BooleanField(default=False)

    priority = models.PositiveSmallIntegerField(default=100)

    # Each registered model is active by default.
    active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    @property
    def is_active(self):
        """Backward-compatible instance-level alias."""
        return self.active

    @is_active.setter
    def is_active(self, value):
        self.active = value

    @property
    def availability_status(self):
        """Return this model's configured availability status."""

        if not self.active:
            return "disabled"

        config = (
            self.config
            if isinstance(self.config, dict)
            else {}
        )

        configured_status = str(
            config.get("status", "")
        ).strip().lower()

        if (
            config.get("coming_soon") is True
            or configured_status in COMING_SOON_STATUSES
        ):
            return "coming_soon"

        return "available"

    @property
    def is_available_for_inference(self):
        """
        Indicate whether this model is marked available.

        API credentials and model access must still be verified
        by the inference service.
        """
        return self.availability_status == "available"

    class Meta:
        ordering = ["priority", "name"]

        constraints = [
            models.UniqueConstraint(
                fields=["provider", "model_id"],
                name="as_unique_provider_model",
            ),
        ]

        indexes = [
            models.Index(
                fields=["provider", "active"],
                name="as_provider_active_idx",
            ),
        ]

    def __str__(self):
        return f"{self.name} ({self.provider})"


class AIRequest(models.Model):
    """
    Operational record for each AI request.
    Monetary cost is deliberately not tracked here.
    """

    class TaskCategory(models.TextChoices):
        GENERAL = "general", "General"
        CODING = "coding", "Coding"
        RESEARCH = "research", "Research"
        REASONING = "reasoning", "Reasoning"
        WRITING = "writing", "Writing"
        VISION = "vision", "Vision"
        OTHER = "other", "Other"

    class StatusChoices(models.TextChoices):
        PENDING = "pending", "Pending"
        PROCESSING = "processing", "Processing"
        SUCCEEDED = "succeeded", "Succeeded"
        FAILED = "failed", "Failed"
        CANCELLED = "cancelled", "Cancelled"

    class ModeChoices(models.TextChoices):
        AUTO = "auto", "Auto"
        THINK = "think", "Think"

    request_id = models.UUIDField(
        default=uuid.uuid4,
        unique=True,
        editable=False,
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ai_requests",
    )

    selected_model = models.ForeignKey(
        ModelRegistry,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="requests",
    )

    # Snapshots preserve which model handled the request.
    provider = models.CharField(max_length=50, blank=True)
    model_name = models.CharField(max_length=255, blank=True)

    task_category = models.CharField(
        max_length=20,
        choices=TaskCategory.choices,
        default=TaskCategory.GENERAL,
    )

    requested_mode = models.CharField(
        max_length=10,
        choices=ModeChoices.choices,
        default=ModeChoices.AUTO,
    )

    web_search_used = models.BooleanField(default=False)
    fallback_used = models.BooleanField(default=False)

    status = models.CharField(
        max_length=15,
        choices=StatusChoices.choices,
        default=StatusChoices.PENDING,
    )

    input_tokens = models.PositiveIntegerField(
        null=True,
        blank=True,
    )

    output_tokens = models.PositiveIntegerField(
        null=True,
        blank=True,
    )

    response_time_ms = models.PositiveIntegerField(
        null=True,
        blank=True,
    )

    # Store safe error codes only.
    error_code = models.CharField(max_length=100, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    completed_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    class Meta:
        ordering = ["-created_at"]

        indexes = [
            models.Index(
                fields=["created_at", "status"],
                name="as_request_status_idx",
            ),
            models.Index(
                fields=["task_category", "created_at"],
                name="as_task_created_idx",
            ),
        ]

    def __str__(self):
        return f"{self.request_id} - {self.status}"


class EvaluationResult(models.Model):
    """
    Stores benchmark and quality evaluation results
    for registered AI models.
    """

    model = models.ForeignKey(
        ModelRegistry,
        on_delete=models.CASCADE,
        related_name="evaluation_results",
    )

    benchmark_name = models.CharField(max_length=150)

    task_category = models.CharField(
        max_length=20,
        choices=AIRequest.TaskCategory.choices,
        default=AIRequest.TaskCategory.GENERAL,
    )

    score = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
    )

    passed = models.BooleanField(
        null=True,
        blank=True,
    )

    latency_ms = models.PositiveIntegerField(
        null=True,
        blank=True,
    )

    input_tokens = models.PositiveIntegerField(
        null=True,
        blank=True,
    )

    output_tokens = models.PositiveIntegerField(
        null=True,
        blank=True,
    )

    result_summary = models.TextField(blank=True)

    evaluated_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-evaluated_at"]

        indexes = [
            models.Index(
                fields=["model", "evaluated_at"],
                name="as_eval_model_date_idx",
            ),
        ]

    def __str__(self):
        return f"{self.model.name} - {self.benchmark_name}"