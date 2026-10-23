
# OmaxasAI Backend Architecture

## 1. Overview

OmaxasAI is a Django REST Framework backend designed to provide AI
conversations, model routing, user accounts, document-based knowledge
retrieval, image-generation requests, and model discovery.

The backend is organized into Django applications, shared utilities,
infrastructure modules, and deployment configuration.

This document describes the intended architecture and identifies components
that still require integration or verification. A component being present in
the codebase does not necessarily mean its complete end-to-end workflow is
operational.

## 2. Technology Stack

| Component | Technology |
|---|---|
| Backend framework | Django |
| API framework | Django REST Framework |
| Authentication | JSON Web Tokens using SimpleJWT |
| Development database | SQLite |
| Production database | PostgreSQL, when configured |
| Environment configuration | python-dotenv |
| AI provider integration | LiteLLM and OpenAI SDK |
| Document extraction | pypdf and python-docx |
| Image validation | Pillow |
| API access control | DRF authentication and permissions |

Package versions are specified in the requirements files. The installed
versions and compatibility must be verified in the development environment
before deployment.

## 3. High-Level Architecture

```text
Frontend / API Client
        |
        v
Django URL Router
        |
        v
Django REST Framework Views
        |
        +--------------------+
        |                    |
        v                    v
Authentication          Input Validation
and Permissions         Serializers
        |                    |
        +----------+---------+
                   |
                   v
             Application Services
                   |
       +-----------+-----------+
       |           |           |
       v           v           v
   AI Services  Knowledge    Image Services
       |         Services        |
       v           |             v
   AI Providers    v        Image Storage
               Embeddings
               and Retrieval
       |           |             |
       +-----------+-------------+
                   |
                   v
             Database / Storage
```

The diagram represents the intended architecture. Every connection shown
must be verified against the current implementation before being considered
production-ready.

## 4. Project Structure

```text
OMAXAS AI BD/
├── manage.py
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
│   │   ├── services/
│   │   └── providers/
│   ├── conversations/
│   │   └── services/
│   ├── knowledge/
│   │   └── services/
│   ├── images/
│   │   └── services/
│   └── explore/
├── common/
├── infrastructure/
├── requirements/
├── tests/
├── docs/
└── deployment/
```

## 5. Application Responsibilities

### 5.1 Accounts

The Accounts application manages user identity and preferences.

Responsibilities:

- User registration and authentication.
- Email-based account identity.
- JWT access and refresh tokens.
- User profile retrieval and updates.
- User preferences such as theme and language.

The custom user model uses email as its primary login identifier.

### 5.2 Assistant

The Assistant application provides the central AI response workflow.

Responsibilities:

- Validate assistant prompts.
- Classify user tasks.
- Select a suitable registered AI model.
- Route requests to configured providers.
- Track request status and response metadata.
- Record model evaluation results.

The model registry stores public model information, capabilities, provider
identifiers, and configuration metadata. Provider credentials must be read
from environment variables rather than stored as plaintext secrets in the
database.

The model router and provider implementations must be verified together
before relying on automatic fallback behavior.

### 5.3 Conversations

The Conversations application manages chat history and related user data.

Responsibilities:

- Create and list conversations.
- Store user and assistant messages.
- Retrieve message history.
- Search conversations and messages.
- Store attachment metadata.
- Collect message feedback.

Conversation queries must be restricted to the authenticated owner.

The chat service and history service are separate modules. Their integration
with the API views and AI provider must be verified.

### 5.4 Knowledge

The Knowledge application supports document-based retrieval.

Intended processing workflow:

1. Accept a supported document or text source.
2. Validate the input and enforce size limits.
3. Extract readable text.
4. Divide the text into overlapping chunks.
5. Generate embeddings for the chunks.
6. Store chunks and embedding metadata.
7. Embed a user's question.
8. Rank relevant chunks by cosine similarity.
9. Return relevant content to the assistant.

The current design stores embedding vectors in a JSON field. This is suitable
for an initial implementation but is not an optimized vector-search solution
for a large document collection.

PostgreSQL with pgvector or a dedicated vector database can be considered
when the retrieval workload requires it.

URL ingestion must not be enabled without protections against server-side
request forgery, private-network access, and unsafe redirects.

### 5.5 Images

The Images application manages image-generation requests and generated image
metadata.

Intended workflow:

1. Authenticate the user.
2. Validate the prompt and output settings.
3. Create a generation request.
4. Call the configured image provider.
5. Validate returned image bytes and dimensions.
6. Store image files through Django's configured storage backend.
7. Save image metadata and update request status.
8. Allow the owner to retrieve their generation history.

The current image service is synchronous. Production use should consider
background task processing, request timeouts, concurrency limits, retry
policies, and cleanup of partially saved files.

The image-generation service must be connected to the API view before a
request created through the API can trigger actual generation.

### 5.6 Explore

The Explore application provides discovery endpoints for active AI models,
providers, capabilities, and application features.

Responsibilities:

- Search public model metadata.
- Filter by model capabilities.
- Aggregate registered providers.
- Report feature integration status.

Explore responses must not disclose API keys, private endpoints, or internal
provider configuration.

## 6. Shared Utilities

The `common` package contains reusable components:

| Module | Responsibility |
|---|---|
| `common/exceptions.py` | Standard API exception handling |
| `common/pagination.py` | Reusable pagination classes |
| `common/permissions.py` | Ownership and access-control helpers |
| `common/response.py` | Consistent success-response helpers |

These utilities only affect endpoints that explicitly use them or are
configured to use them globally.

The exception handler must be registered in Django REST Framework settings.
Pagination classes must be applied to the relevant list views.
Permissions must be reviewed for each endpoint.

Changing response formats globally should be treated as an API compatibility
change.

## 7. Infrastructure

The `infrastructure` package is intended to hold utilities shared across
applications.

- `infrastructure/logging.py` defines centralized logging configuration.
- `infrastructure/storage.py` provides shared file-storage utilities.

These modules require integration with Django settings and the relevant
application services. Storage utilities must not replace application-specific
validation or authorization.

## 8. Database Design

The primary database stores users, preferences, conversations, messages,
registered AI models, AI request metadata, knowledge documents, text chunks,
image-generation requests, and generated-image metadata.

Ownership relationships should be enforced through foreign keys and
owner-scoped queryset filtering.

SQLite may be used for local development and tests. PostgreSQL is the
intended production option when configured through environment variables.

Database migrations must be generated from the final model definitions and
reviewed before applying them to a shared or production database.

## 9. Authentication and Request Lifecycle

A typical protected API request follows these steps:

1. The client sends an access token in the Authorization header.
2. JWT authentication validates the token.
3. DRF permissions determine whether the request is allowed.
4. The serializer validates incoming data.
5. The view invokes the appropriate application service.
6. The service interacts with models, storage, or external providers.
7. The view returns the API response.

Ownership checks must be applied to reads, updates, downloads, and deletion.
A valid JWT alone does not grant access to another user's resources.

## 10. External Services and Secrets

External-service configuration belongs in environment variables.

Examples include:

- `DJANGO_SECRET_KEY`
- `DJANGO_DEBUG`
- `DJANGO_ALLOWED_HOSTS`
- `OPENAI_API_KEY`
- `OMAXASAI_IMAGE_MODEL`
- `OMAXASAI_EMBEDDING_MODEL`
- `OMAXASAI_EMBEDDING_API_KEY_ENV`
- `TAVILY_API_KEY`
- Database connection settings

Only variables actually supported by the implemented services should be
configured as required settings.

The `.env` file must not be committed to version control. Use `.env.example`
for placeholder names and safe example values.

## 11. Deployment Architecture

The intended deployment configuration separates:

- Django application serving.
- PostgreSQL database access.
- Media and generated-image storage.
- External AI provider calls.
- Optional model-serving infrastructure.

Production deployment must use production settings, a strong secret key,
HTTPS, appropriate allowed hosts, secure cookies, controlled CORS origins,
and properly configured static and media storage.

The application should not rely on Django's development server in production.

## 12. Current Integration Status

The following work must be verified before claiming a complete production
implementation:

- Registering the custom exception handler and logging configuration.
- Applying pagination consistently to the required list endpoints.
- Connecting the conversation service modules to the actual chat views.
- Completing the document extraction, chunking, embedding, and retrieval
  pipeline.
- Connecting image-generation requests to the image-generation service.
- Verifying AI provider routing, credentials, fallback, and error handling.
- Completing root-level integration tests.
- Reviewing production settings, storage, and deployment configuration.

## 13. Testing Strategy

Testing should cover:

- Registration, password validation, and JWT authentication.
- User ownership and permission boundaries.
- Conversation and message persistence.
- Model classification and provider routing.
- Document validation and text extraction.
- Chunk creation, embedding validation, and retrieval ranking.
- Image output validation and storage cleanup.
- API status codes and response schemas.
- Production configuration and security-related behavior.

Unit tests should mock external AI providers. Separate integration tests can
be used for provider connectivity when credentials and API access are
available.

## 14. Architectural Principles

The OmaxasAI backend follows these principles:

- Separate API views from business logic.
- Keep credentials outside source code and database metadata.
- Enforce authentication and resource ownership.
- Validate files and external provider responses.
- Use reusable utilities where they offer genuine consistency.
- Keep external-provider failures from exposing sensitive information.
- Test integration boundaries before production deployment.
- Document unfinished integrations instead of treating them as complete.

