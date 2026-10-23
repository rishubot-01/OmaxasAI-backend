
# Use a slim Python image for the Django backend.
FROM python:3.13-slim-bookworm

# Keep Python output visible in container logs.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    DJANGO_SETTINGS_MODULE=config.settings.production \
    DJANGO_DEBUG=False

# Set the application working directory.
WORKDIR /app

# Install production dependencies first for better build caching.
COPY requirements/ ./requirements/

RUN python -m pip install --no-cache-dir --upgrade pip \
    && python -m pip install --no-cache-dir -r requirements/production.txt \
    && python -m pip check

# Create a non-root application user.
RUN addgroup --system app \
    && adduser --system --ingroup app --home /app app

# Copy only application files needed at runtime.
# This intentionally does not copy the root .env file.
COPY --chown=app:app manage.py ./manage.py
COPY --chown=app:app config/ ./config/
COPY --chown=app:app apps/ ./apps/
COPY --chown=app:app common/ ./common/
COPY --chown=app:app infrastructure/ ./infrastructure/
COPY --chown=app:app deployment/backend/entrypoint.sh ./deployment/backend/entrypoint.sh

# Prepare directories for collected static files and local media storage.
RUN mkdir -p /app/staticfiles /app/media \
    && chown -R app:app /app \
    && chmod 755 /app/deployment/backend/entrypoint.sh

# Do not run the application as root.
USER app

# Django application port.
EXPOSE 8000

# Run startup preparation, then launch Gunicorn.
ENTRYPOINT ["/app/deployment/backend/entrypoint.sh"]

CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3", "--timeout", "120", "--access-logfile", "-", "--error-logfile", "-"]

