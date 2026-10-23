
#!/bin/sh

# Stop immediately if a command fails or an unset variable is used.
set -eu

echo "Starting OmaxasAI backend..."

# Verify that Django can load its configured settings and applications.
echo "Checking Django configuration..."
python manage.py check

# Collect static assets into STATIC_ROOT for production serving.
echo "Collecting static files..."
python manage.py collectstatic --noinput

# Start the application server with the arguments supplied by Docker.
echo "Starting Gunicorn..."
exec "$@"

