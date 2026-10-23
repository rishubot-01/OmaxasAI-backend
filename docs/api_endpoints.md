
# OmaxasAI API Endpoints

## 1. Overview

OmaxasAI exposes REST APIs through Django REST Framework.

Local development base URL:

    http://127.0.0.1:8000

The API routes below are based on the current project URL configuration.
Conversation sub-routes should be checked against
`apps/conversations/urls.py` before publishing this document as the final API
contract.

## 2. Authentication

Protected endpoints use JSON Web Token (JWT) authentication.

After logging in, send the access token in the Authorization header:

    Authorization: Bearer <access_token>

The access token should be sent with every protected API request.

### Authentication endpoints

| Method | Endpoint | Description | Authentication |
|---|---|---|---|
| POST | `/api/auth/register/` | Register a new user | Public |
| POST | `/api/auth/token/` | Obtain access and refresh tokens | Public |
| POST | `/api/auth/token/refresh/` | Obtain a new access token | Refresh token |
| POST | `/api/auth/token/verify/` | Verify a JWT token | Public endpoint; token required in body |

### Registration example

Request:

```json
{
  "email": "user@example.com",
  "password": "StrongPassword!123",
  "password_confirm": "StrongPassword!123",
  "display_name": "OmaxasAI User"
}
```

The registration serializer validates the email, password, and password
confirmation. Exact required fields are determined by the current serializer.

### Login example

Request:

```json
{
  "email": "user@example.com",
  "password": "StrongPassword!123"
}
```

A successful SimpleJWT token response normally contains:

```json
{
  "refresh": "<refresh_token>",
  "access": "<access_token>"
}
```

Never expose either token in public logs or share it with other users.

## 3. Accounts

### User profile and preferences

| Method | Endpoint | Description | Authentication |
|---|---|---|---|
| GET | `/api/accounts/me/` | Retrieve the current user's profile | Required |
| PATCH | `/api/accounts/me/` | Partially update the current user's profile | Required |
| PUT | `/api/accounts/me/` | Update the current user's profile | Required |
| GET | `/api/accounts/preferences/` | Retrieve user preferences | Required |
| PATCH | `/api/accounts/preferences/` | Partially update preferences | Required |
| PUT | `/api/accounts/preferences/` | Update preferences | Required |

Only the authenticated user's profile and preferences may be accessed through
these endpoints.

The exact set of editable fields is controlled by the account serializers.

## 4. Assistant

Base path:

    /api/assistant/

| Method | Endpoint | Description | Authentication |
|---|---|---|---|
| POST | `/api/assistant/chat/` | Generate an AI response | Required |
| GET | `/api/assistant/models/` | List active registered models | Required |
| GET | `/api/assistant/requests/` | Retrieve the authenticated user's AI request history | Required |

### Chat request example

Request:

```json
{
  "message": "Explain Python classes with an example.",
  "mode": "auto",
  "web_search": false,
  "stream": false
}
```

Supported input options in the prompt serializer include:

- `message`: Required prompt text.
- `mode`: `auto` or `think`.
- `web_search`: Whether web search is requested.
- `stream`: Whether streaming is requested.
- `conversation_id`: Optional conversation reference.

The exact response depends on the current view and AI service integration.

Web search and streaming must not be assumed operational until their complete
provider-to-API workflows have been verified.

## 5. Conversations

Base path:

    /api/conversations/

The intended endpoints are listed below. Confirm each route string against
`apps/conversations/urls.py` before relying on it.

| Method | Endpoint | Description | Authentication |
|---|---|---|---|
| GET | `/api/conversations/` | List the current user's conversations | Required |
| POST | `/api/conversations/` | Create a conversation | Required |
| GET | `/api/conversations/<conversation_id>/` | Retrieve conversation details | Required |
| PUT/PATCH | `/api/conversations/<conversation_id>/` | Update an owned conversation, if supported | Required |
| DELETE | `/api/conversations/<conversation_id>/` | Delete an owned conversation, if supported | Required |
| GET | `/api/conversations/<conversation_id>/messages/` | Retrieve conversation messages | Required |
| POST | `/api/conversations/<conversation_id>/send/` | Send a message to the assistant | Required |
| GET/POST | `/api/conversations/<conversation_id>/attachments/` | Access attachment metadata, subject to implemented methods | Required |
| GET/POST | `/api/conversations/<conversation_id>/feedback/` | List or submit message feedback, subject to implemented methods | Required |

The placeholder `<conversation_id>` must be replaced with the relevant
conversation identifier.

Conversation IDs and message IDs must not be treated as authorization.
Every request must verify ownership.

## 6. Knowledge

Base path:

    /api/knowledge/

| Method | Endpoint | Description | Authentication |
|---|---|---|---|
| GET | `/api/knowledge/` | List the current user's documents | Required |
| POST | `/api/knowledge/` | Create a document using an upload, URL, or text source | Required |
| GET | `/api/knowledge/<document_id>/` | Retrieve an owned document | Required |
| DELETE | `/api/knowledge/<document_id>/` | Delete an owned document | Required |

### Text-source request example

```json
{
  "title": "Python Notes",
  "source_type": "text",
  "source_text": "Python supports object-oriented programming."
}
```

### File upload

File uploads should use `multipart/form-data`.

The current serializer defines basic extension, reported MIME type, and size
validation. These checks do not replace content-level file validation.

The intended knowledge pipeline is:

1. Upload or create a source document.
2. Extract text.
3. Create document chunks.
4. Generate embeddings.
5. Retrieve relevant chunks for a search query.

The endpoints above currently describe document management. Do not assume
that the complete processing and semantic retrieval pipeline is exposed
through an API until it has been implemented and tested.

## 7. Images

Base path:

    /api/images/

| Method | Endpoint | Description | Authentication |
|---|---|---|---|
| GET | `/api/images/` | List the current user's image-generation requests | Required |
| POST | `/api/images/` | Create an image-generation request | Required |
| GET | `/api/images/<request_id>/` | Retrieve a request and its associated images | Required |

`<request_id>` is the UUID of an image-generation request.

### Image-generation request example

```json
{
  "prompt": "A cinematic futuristic city at sunset",
  "style": "cinematic",
  "aspect_ratio": "16:9",
  "resolution": "1536x1024",
  "output_format": "png",
  "requested_count": 1
}
```

Supported values must match the choices defined in the image-generation
models and serializers.

The current request-creation view does not automatically execute image
generation unless it explicitly invokes the generation service. The service
integration must be verified before this endpoint is described as generating
images end to end.

## 8. Explore

Base path:

    /api/explore/

| Method | Endpoint | Description | Authentication |
|---|---|---|---|
| GET | `/api/explore/models/` | List and filter active AI models | Public |
| GET | `/api/explore/providers/` | List providers and their active model counts | Public |
| GET | `/api/explore/features/` | List feature descriptions and status | Public |

### Model search and filters

Example:

    GET /api/explore/models/?query=openai

Other available filters defined by the search serializer include:

- `category`
- `capability`
- `supports_vision`
- `supports_streaming`
- `supports_tools`

Example:

    GET /api/explore/models/?capability=vision

Only public-safe registered model information should be returned. Provider
credentials, private endpoints, and internal configuration must not be
exposed.

## 9. General API Behavior

Protected requests should include:

    Authorization: Bearer <access_token>

JSON requests should use:

    Content-Type: application/json

File uploads should use:

    Content-Type: multipart/form-data

Common status codes include:

| Status | Meaning |
|---|---|
| 200 | Request succeeded |
| 201 | Resource created |
| 202 | Request accepted for processing |
| 204 | Request succeeded with no response body |
| 400 | Invalid request data |
| 401 | Authentication required or invalid |
| 403 | Operation forbidden |
| 404 | Resource not found or not accessible |
| 409 | Resource-state conflict |
| 429 | Rate limit exceeded, if configured |
| 500 | Unexpected server error |
| 502 | Upstream service failure |
| 503 | Service temporarily unavailable |

Actual status codes and response schemas depend on the configured view,
serializer, exception handler, and middleware.

## 10. Security Requirements

- Never place API keys in request bodies unless a specific secure workflow
  explicitly requires it.
- Do not return raw exception details, stack traces, or credentials.
- Enforce user ownership for conversations, documents, attachments, feedback,
  and generated images.
- Validate uploaded file content, not only the filename or reported MIME type.
- Protect URL fetching against server-side request forgery.
- Apply appropriate request size limits and rate limits.
- Do not expose private storage keys or external provider credentials.
- Configure CORS and trusted origins for the actual deployment environment.

## 11. Integration Checklist

Before declaring the API ready for production, verify:

- All URL patterns resolve to the intended views.
- JWT registration, login, refresh, and verification work.
- Protected endpoints reject anonymous requests.
- User A cannot access User B's resources.
- Request serializers reject malformed input.
- AI provider calls and fallback behavior work as designed.
- Conversation history is integrated into chat generation where required.
- Knowledge ingestion, embedding, and retrieval are connected end to end.
- Image requests invoke the image-generation service.
- Streaming works through both the provider and API response.
- Pagination and common response formatting are applied consistently where intended.
- API tests pass against the configured database.

