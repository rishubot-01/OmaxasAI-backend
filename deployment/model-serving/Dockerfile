
# Use the official vLLM OpenAI-compatible serving image.
# For production, pin this to a tested version tag.
ARG VLLM_BASE_IMAGE=vllm/vllm-openai:latest
FROM ${VLLM_BASE_IMAGE}

# Keep model downloads and cache in the container's Hugging Face cache.
ENV HF_HOME=/root/.cache/huggingface \
    PYTHONUNBUFFERED=1

WORKDIR /opt/omaxasai

# Copy the vLLM serving configuration.
# This file will be created in the next step.
COPY deployment/model-serving/model_config.yaml /etc/omaxasai/model_config.yaml

# vLLM serves its OpenAI-compatible API on port 8000 by default.
EXPOSE 8000

# The official vLLM image provides the vLLM serving entrypoint.
# Run with the model configuration file.
CMD ["--config", "/etc/omaxasai/model_config.yaml"]

