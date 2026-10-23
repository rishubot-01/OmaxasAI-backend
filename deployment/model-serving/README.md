
# OmaxasAI Backend

OmaxasAI is a Django REST Framework backend project designed to support
user accounts, AI conversations, model routing, document-based knowledge
retrieval, image generation, and model discovery.

Some integrations may still require implementation and testing. Refer to
the project documentation and current source code before treating a feature
as production-ready.

## Features

- Django REST Framework APIs
- JWT authentication using SimpleJWT
- Custom email-based user model
- Conversation and message storage
- AI model registry and routing
- Optional external AI provider integration
- Document processing and retrieval architecture
- Image-generation service architecture
- Explore endpoints for model discovery
- Separate development, testing, and production settings
- Optional Docker deployment

## Technology Stack

- Python
- Django
- Django REST Framework
- SimpleJWT
- SQLite for local development
- PostgreSQL when configured for deployment
- LiteLLM and OpenAI SDK for AI integrations
- pypdf and python-docx for document processing
- Pillow for image validation
- Docker for optional container deployment

## Project Structure

```text
OMAXAS AI BD/
├── manage.py
├── .env
├── .env.example
├── requirements/
│   ├── base.txt
│   ├── development.txt
│   ├── production.txt
│   ├── ai.txt
│   └── testing.txt
├── config/
│   ├── urls.py
│   ├── asgi.py
│   ├── wsgi.py
│   └── settings/
│       ├── base.py
│       ├── development.py
│       ├── production.py
│       └── testing.py
├── apps/
│   ├── accounts/
│   ├── assistant/
│   ├── conversations/
│   ├── knowledge/
│   ├── images/
│   └── explore/
├── common/
├── infrastructure/
├── tests/
├── docs/
└── deployment/
```

## Requirements

Install the following before starting development:

- A compatible Python version
- pip
- Git, if using version control
- A terminal such as PowerShell on Windows

Docker and a compatible GPU are needed only if you intend to run the
optional self-hosted vLLM model server.

## 1. Open the Project Directory

In Windows PowerShell:

```powershell
cd "C:\Users\Rishu kumar\OMAXAS AI BD"
```

## 2. Create a Virtual Environment

If the project already has a `.venv` directory, you can reuse it.

To create one:

```powershell
python -m venv .venv
```

Activate it in PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
```

If PowerShell blocks activation, use an approved execution-policy adjustment
for your user account or activate the environment using another supported
method. Do not disable security controls unnecessarily.

## 3. Install Dependencies

Install the base requirements:

```powershell
python -m pip install --upgrade pip
python -m pip install -r requirements/base.txt
```

For development, install the development requirements if that file is
configured correctly:

```powershell
python -m pip install -r requirements/development.txt
```

Do not install every requirements file blindly. Production, AI, and testing
files may have different purposes or overlapping dependencies.

After installation, check for dependency conflicts:

```powershell
python -m pip check
```

## 4. Configure Environment Variables

Create a local `.env` file in the project root if it does not already exist.

Use `.env.example` as a reference, but replace placeholders with appropriate
local values. Never commit actual secrets.

Typical settings include:

```dotenv
DJANGO_SECRET_KEY=replace-with-a-long-random-development-secret
DJANGO_DEBUG=True
DJANGO_ALLOWED_HOSTS=127.0.0.1,localhost,testserver

DB_ENGINE=sqlite

OPENAI_API_KEY=
TAVILY_API_KEY=
```

Only configure variables that are supported by the current implementation.
Some AI providers, image services, and database options may require additional
settings.

For local development, SQLite is the simplest starting point. Production
should use a properly configured database and protected credentials.

## 5. Check Django Configuration

The project's `manage.py` is configured to use development settings.

Run:

```powershell
python manage.py check
```

Resolve any import, settings, or model errors before continuing.

## 6. Create and Apply Database Migrations

Once the models and app configuration have been reviewed, generate migrations:

```powershell
python manage.py makemigrations
```

Inspect the generated migrations before applying them.

For the local development database:

```powershell
python manage.py migrate
```

Do not apply unreviewed migrations to a production database. Back up important
data and test schema changes in a staging environment first.

## 7. Create an Administrator

After the database migrations have been applied:

```powershell
python manage.py createsuperuser
```

Follow the prompts to configure the administrator account.

The Django admin interface is normally available at:

    http://127.0.0.1:8000/admin/

Admin access must be secured before deploying to production.

## 8. Start the Development Server

Run:

```powershell
python manage.py runserver
```

The local server normally listens at:

    http://127.0.0.1:8000/

This server is intended for development, not production hosting.

## API Documentation

The API endpoints and authentication requirements are documented in:

- `docs/api_endpoints.md`
- `docs/architecture.md`
- `docs/database_schema.md`
- `docs/security.md`

Use the actual URL patterns and serializers as the source of truth when
checking endpoint paths and request formats.

Protected endpoints generally require a JWT access token in the header:

```http
Authorization: Bearer <access_token>
```

## Testing

Run Django's configured system checks:

```powershell
python manage.py check
```

Run the project's test suite:

```powershell
python manage.py test
```

If tests use the dedicated testing settings module, run them explicitly:

```powershell
python manage.py test --settings=config.settings.testing
```

Fix import errors, model issues, and failing tests before deployment.

Tests involving external AI services should use mocks unless the test is
specifically designed to verify a real provider connection.

## Optional Self-Hosted Model Serving

The optional model-serving configuration is located in:

    deployment/model-serving/

It uses vLLM to expose a compatible model API.

Before running it, verify:

- GPU and driver compatibility
- Model license and hardware requirements
- The vLLM image version
- The `model_config.yaml` options
- Model access credentials, if required
- Network isolation and API authentication

See:

    deployment/model-serving/README.md

The model server is a separate service and is not automatically connected
to Django merely because its container is running.

## Docker Backend Deployment

The backend container files are located in:

    deployment/backend/

Before building, verify that:

- `requirements/production.txt` exists and contains the needed dependencies.
- `deployment/backend/entrypoint.sh` is present.
- Production environment variables are configured.
- The application can load `config.settings.production`.
- Static and media storage are configured appropriately.

Build the backend image from the project root:

```powershell
docker build -f deployment/backend/Dockerfile -t omaxasai-backend .
```

Run it only after configuring the required production environment variables
and database connectivity.

Do not put secrets in the Dockerfile or copy a real `.env` file into the
container image.

## Security

- Never commit `.env` or real credentials.
- Use a strong production `DJANGO_SECRET_KEY`.
- Set `DEBUG=False` in production.
- Configure `ALLOWED_HOSTS`, CORS, and CSRF trusted origins explicitly.
- Use HTTPS in production.
- Protect user-owned resources with authorization checks.
- Validate uploaded files and generated image content.
- Keep private files and provider credentials out of public API responses.
- Restrict access to any self-hosted model server.
- Review dependencies and migrations before deployment.

Refer to `docs/security.md` for further requirements.

## Current Implementation Status

The repository contains the structure for the features described above,
but the presence of a module does not guarantee that its full workflow is
operational.

Before a production release, verify:

- Authentication and user ownership tests
- AI provider configuration and model routing
- Conversation history integration
- Document extraction, chunking, embeddings, and retrieval
- Image-generation provider integration
- Explore filtering and pagination
- Production settings and storage
- Docker builds and deployment configuration

## License

Add the project's selected license before distributing the source code
or accepting external contributions.

