
# OmaxasAI Database Schema

## 1. Overview

This document describes the intended database schema for the OmaxasAI
backend.

The schema is organized around user accounts, AI model routing,
conversations, document-based knowledge retrieval, and image generation.

The Django model definitions are the source of truth. Any differences
between this document and the final model definitions must be resolved
before generating and applying production migrations.

## 2. Entity Relationship Overview

```text
User
 |
 +-- UserPreference
 |
 +-- Conversation
 |     |
 |     +-- Message
 |     |     |
 |     |     +-- Feedback
 |     |     |
 |     |     +-- FileAttachment
 |     |
 |     +-- FileAttachment
 |
 +-- AIRequest
 |
 +-- KnowledgeDocument
 |     |
 |     +-- DocumentChunk
 |
 +-- ImageGenerationRequest
       |
       +-- GeneratedImage

ModelRegistry
 |
 +-- AIRequest
 |
 +-- EvaluationResult
```

The relationships above describe the intended ownership and reference
structure. Explore uses the registered models from the Assistant app and
does not require a separate Explore database model in the current design.

## 3. Accounts

### 3.1 User

Table name: Django-generated table for the custom `accounts.User` model.

Purpose: Store user identity, authentication details, and account status.

| Field | Type | Description |
|---|---|---|
| id | Big integer primary key | Internal user identifier |
| email | Unique email | Primary login identifier |
| password | Hashed password | Django password hash |
| display_name | String, max 80 | Public display name |
| is_email_verified | Boolean | Email verification status |
| is_active | Boolean | Whether login is allowed |
| is_staff | Boolean | Staff/admin access flag |
| is_superuser | Boolean | Django superuser flag |
| date_joined | Date/time | Account creation date |
| last_login | Date/time, nullable | Last successful login |
| created_at | Date/time | Record creation timestamp |
| updated_at | Date/time | Last record update |

The custom user model inherits additional fields from Django's
`AbstractUser`, except for `username`, which is removed.

The email field is the configured `USERNAME_FIELD`.

Passwords must be stored using Django's password hashing system.
Plaintext passwords must never be stored.

### 3.2 UserPreference

Purpose: Store settings associated with an individual user.

Relationship: One-to-one with User.

| Field | Type | Description |
|---|---|---|
| id | Big integer primary key | Preference record identifier |
| user_id | Foreign key, unique | Associated user |
| theme | Choice | `system`, `light`, or `dark` |
| language | String, max 10 | Preferred language |
| default_mode | Choice/string | Default assistant mode |
| web_search_enabled | Boolean | User's web-search preference |
| created_at | Date/time | Record creation timestamp |
| updated_at | Date/time | Last update timestamp |

Deleting a user deletes the associated preference record.

## 4. Assistant

### 4.1 ModelRegistry

Purpose: Register AI models that may be used by the model router.

| Field | Type | Description |
|---|---|---|
| id | Big integer primary key | Registry record identifier |
| name | String | Display name |
| provider | Choice/string | Provider identifier |
| model_id | String | Provider model identifier |
| backend_type | Choice | External API or self-hosted backend |
| endpoint_url | URL/string, optional | Configured model endpoint |
| credential_env_var | String | Name of the environment variable containing a credential |
| capabilities | JSON | Supported task capabilities |
| config | JSON | Additional model configuration |
| context_window | Integer | Model context limit, when known |
| supports_streaming | Boolean | Whether streaming is supported |
| supports_vision | Boolean | Whether image input is supported |
| supports_tools | Boolean | Whether tools are supported |
| priority | Integer | Routing priority |
| active | Boolean | Whether the model is enabled |
| created_at | Date/time | Record creation timestamp |
| updated_at | Date/time | Last update timestamp |

A uniqueness constraint applies to the combination of `provider` and
`model_id`.

An index supports provider and active-status queries.

Provider secrets must not be stored as plaintext in `config` or
`credential_env_var`. The latter stores a variable name, not its secret value.

### 4.2 AIRequest

Purpose: Track an assistant request and its execution metadata.

| Field | Type | Description |
|---|---|---|
| id | Big integer primary key | Internal record identifier |
| request_id | UUID, unique | Public request correlation identifier |
| user_id | Nullable foreign key | Requesting user, if available |
| selected_model_id | Nullable foreign key | Selected registered model |
| provider | String | Provider snapshot |
| model_name | String | Model identifier snapshot |
| category | Choice | Task category |
| mode | Choice | `auto` or `think` |
| web_search_used | Boolean | Whether web search was used |
| fallback_used | Boolean | Whether provider fallback occurred |
| status | Choice | Request processing status |
| input_tokens | Nullable integer | Input token count, when available |
| output_tokens | Nullable integer | Output token count, when available |
| response_time_ms | Nullable integer | Response duration |
| error_code | String | Safe error identifier |
| created_at | Date/time | Record creation timestamp |
| updated_at | Date/time | Last update timestamp |

Possible request statuses include pending, processing, succeeded, failed,
and cancelled.

The model should record operational metadata without storing sensitive
credentials. Retention policies for prompts, outputs, and identifiers
should be defined separately.

### 4.3 EvaluationResult

Purpose: Record model benchmark and evaluation outcomes.

| Field | Type | Description |
|---|---|---|
| id | Big integer primary key | Evaluation record identifier |
| model_id | Foreign key | Evaluated model |
| benchmark_name | String | Evaluation name |
| task_category | Choice | Evaluated task category |
| score | Nullable decimal | Score from 0 to 100 |
| passed | Nullable boolean | Whether the evaluation passed |
| latency_ms | Nullable integer | Observed latency |
| input_tokens | Nullable integer | Input tokens |
| output_tokens | Nullable integer | Output tokens |
| summary | Text | Evaluation summary |
| evaluated_at | Date/time | Evaluation timestamp |

Evaluation results belong to a registered model.

## 5. Conversations

### 5.1 Conversation

Purpose: Represent a user's chat thread.

| Field | Type | Description |
|---|---|---|
| id | Big integer primary key | Conversation identifier |
| user_id | Foreign key | Conversation owner |
| title | String | Chat title |
| is_archived | Boolean | Whether the conversation is archived |
| created_at | Date/time | Creation timestamp |
| updated_at | Date/time | Last activity timestamp |

An index on user and update time supports the conversation history view.

Deleting the owning user deletes their conversations.

### 5.2 Message

Purpose: Store user messages and assistant replies.

| Field | Type | Description |
|---|---|---|
| id | Big integer primary key | Message identifier |
| conversation_id | Foreign key | Parent conversation |
| role | Choice | `user` or `assistant` |
| content | Text | Message contents |
| mode | Choice | `auto` or `think` |
| provider | String | Provider used, when known |
| model_name | String | Model used, when known |
| web_search_used | Boolean | Whether web search contributed |
| metadata | JSON | Additional non-secret response metadata |
| created_at | Date/time | Message creation timestamp |
| updated_at | Date/time | Last update timestamp |

Messages are ordered chronologically when returning a conversation.

Message ownership is derived from the owning conversation. An API must verify
that a conversation belongs to the authenticated user before returning or
changing its messages.

### 5.3 FileAttachment

Purpose: Store attachment metadata associated with a conversation.

| Field | Type | Description |
|---|---|---|
| id | Big integer primary key | Attachment identifier |
| conversation_id | Foreign key | Parent conversation |
| message_id | Nullable foreign key | Associated message, if any |
| original_filename | String | Original display filename |
| file_type | Choice | Image, document, audio, video, or other |
| mime_type | String | Reported content type |
| size_bytes | Nullable integer | File size |
| storage_key | String | Internal storage reference |
| storage_provider | String | Storage backend |
| status | Choice | Upload/processing state |
| created_at | Date/time | Creation timestamp |
| updated_at | Date/time | Last update timestamp |

Storage keys must not be exposed in public API responses. File access must
check conversation ownership.

### 5.4 Feedback

Purpose: Store user feedback about assistant messages.

| Field | Type | Description |
|---|---|---|
| id | Big integer primary key | Feedback identifier |
| user_id | Foreign key | Feedback author |
| message_id | Foreign key | Target message |
| rating | Choice | Helpful or unhelpful |
| comment | Text, max 2,000 | Optional comment |
| created_at | Date/time | Creation timestamp |
| updated_at | Date/time | Last update timestamp |

A uniqueness constraint on user and message prevents duplicate feedback
records from the same user for the same message.

The application should ensure that feedback targets an assistant message in
a conversation accessible to the submitting user.

## 6. Knowledge

### 6.1 KnowledgeDocument

Purpose: Represent an uploaded file, URL source, or manually supplied text.

| Field | Type | Description |
|---|---|---|
| id | Big integer primary key | Document identifier |
| owner_id | Foreign key | Document owner |
| title | String, max 200 | Document title |
| description | Text | Optional description |
| source_type | Choice | `upload`, `url`, or `text` |
| file | File field | Stored document, if uploaded |
| original_filename | String | Original filename |
| mime_type | String | Reported MIME type |
| size_bytes | Nullable integer | Document size |
| source_url | URL | Source URL, if applicable |
| source_text | Text | Directly submitted text |
| content_sha256 | String, max 64 | Content hash |
| status | Choice | Upload/processing status |
| error_message | Text | Safe processing error |
| chunk_count | Integer | Number of stored chunks |
| metadata | JSON | Non-secret document metadata |
| processed_at | Nullable date/time | Processing completion time |
| created_at | Date/time | Creation timestamp |
| updated_at | Date/time | Last update timestamp |

An index on owner and status supports filtering. An additional index on owner
and creation time supports document history queries.

Document-source validation must match the selected source type.

### 6.2 DocumentChunk

Purpose: Store extracted document text in searchable segments.

| Field | Type | Description |
|---|---|---|
| id | Big integer primary key | Chunk identifier |
| document_id | Foreign key | Parent document |
| chunk_index | Integer | Position within the document |
| content | Text | Extracted text segment |
| token_count | Nullable integer | Estimated or measured token count |
| embedding | Nullable JSON | Numerical embedding vector |
| embedding_model | String | Embedding model identifier |
| metadata | JSON | Character offsets and other metadata |
| created_at | Date/time | Creation timestamp |

A uniqueness constraint on `document_id` and `chunk_index` prevents duplicate
chunk positions within a document.

Deleting a document deletes its chunks.

Embeddings stored as JSON are straightforward to inspect but do not provide
specialized vector indexing. Large deployments should consider vector-search
infrastructure.

## 7. Images

### 7.1 ImageGenerationRequest

Purpose: Track image-generation requests and their status.

| Field | Type | Description |
|---|---|---|
| id | Big integer primary key | Internal request identifier |
| request_id | Unique UUID | Request correlation identifier |
| user_id | Foreign key | Request owner |
| prompt | Text | Image prompt |
| negative_prompt | Text | Optional exclusions |
| style | Choice | Requested visual style |
| aspect_ratio | Choice | Requested aspect ratio |
| resolution | Choice | Requested resolution preset |
| output_format | Choice | PNG, JPEG, or WebP |
| requested_count | Small integer | Number of images requested |
| generated_count | Small integer | Number successfully generated |
| provider | String | Provider used |
| model_name | String | Image model identifier |
| seed | Nullable integer | Optional generation seed |
| status | Choice | Queued, processing, succeeded, failed, or cancelled |
| generation_parameters | JSON | Non-secret generation settings |
| error_code | String | Safe error identifier |
| error_message | String, max 500 | User-safe error message |
| started_at | Nullable date/time | Processing start |
| completed_at | Nullable date/time | Processing completion |
| duration_ms | Nullable integer | Processing duration |
| created_at | Date/time | Creation timestamp |
| updated_at | Date/time | Last update timestamp |

Indexes support queries by user/status and user/creation time.

### 7.2 GeneratedImage

Purpose: Store each generated image's file reference and metadata.

| Field | Type | Description |
|---|---|---|
| id | Big integer primary key | Image record identifier |
| generation_id | Foreign key | Parent generation request |
| image_index | Small integer | Position in the request's output |
| image_file | Image field | Stored image file |
| image_url | URL | Optional external image reference |
| storage_provider | Choice | Default storage, Cloudinary, or external |
| mime_type | String | Image MIME type |
| file_size_bytes | Nullable integer | Stored image size |
| width | Nullable integer | Image width |
| height | Nullable integer | Image height |
| alt_text | String, max 500 | Accessibility description |
| content_sha256 | String, max 64 | Image content hash |
| is_public | Boolean | Public-visibility flag |
| metadata | JSON | Non-secret image metadata |
| created_at | Date/time | Creation timestamp |
| updated_at | Date/time | Last update timestamp |

A uniqueness constraint on generation and image index prevents duplicate
output positions for a single generation request.

Generated image file access must be consistent with the generation owner's
permissions. The `is_public` flag alone should not bypass API authorization.

## 8. Explore

The Explore application currently reads active `ModelRegistry` records.

It exposes public-safe model information, provider summaries, capabilities,
and feature status. The current design does not define a separate Explore
database model.

## 9. Data Integrity and Indexing

The schema uses:

- Foreign keys for related records.
- Unique email addresses for user identity.
- Unique request UUIDs for AI and image requests.
- Unique provider/model combinations for the model registry.
- Unique document/chunk indexes.
- Unique generation/image indexes.
- Indexes on owner, status, and creation/update timestamps.

Database constraints and model-level validation serve different purposes.
Validation should provide useful errors, while database constraints protect
integrity under concurrent writes.

## 10. Ownership and Access Control

The application must enforce these rules:

1. Users can only list and retrieve their own conversations.
2. Messages may only be accessed through an authorized conversation.
3. Knowledge documents and their chunks belong to a specific owner.
4. Image-generation history is filtered by the authenticated owner.
5. Provider credentials and private storage keys are never exposed.
6. Feedback is associated with the authenticated user and an eligible
   assistant message.
7. Administrative access is governed by Django staff permissions.

A foreign key does not automatically enforce API-level ownership. Views and
services must perform explicit permission checks.

## 11. Migrations

After model definitions are complete and imports pass validation, generate
migrations using:

```powershell
python manage.py makemigrations
```

Review the generated migration files before applying them.

For a local development database, migrations can then be applied using:

```powershell
python manage.py migrate
```

Do not apply unreviewed schema changes to a production database. Back up
production data and test migrations in a staging environment first.

## 12. Schema Maintenance

When a model changes:

1. Update the Django model.
2. Update serializers and related application services.
3. Update this schema document.
4. Generate and review migrations.
5. Update model, API, and integration tests.
6. Validate ownership and deletion behavior.
7. Test against the intended database engine.

This document should be checked against the final models and generated
migrations before the first production release.

