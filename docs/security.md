
# OmaxasAI Security Guidelines

## 1. Purpose

This document describes the security requirements for the OmaxasAI backend.

It covers authentication, authorization, secrets management, file handling,
AI provider integration, database access, logging, and production deployment.

These guidelines describe the required security behavior. A security
control must be tested against the actual implementation before it can be
considered enforced.

## 2. Authentication

OmaxasAI uses Django REST Framework with JSON Web Token authentication.

Protected endpoints should require a valid access token:

    Authorization: Bearer <access_token>

The authentication system must:

- Verify tokens using the configured signing key and algorithm.
- Reject expired or invalid tokens.
- Avoid accepting access tokens from untrusted locations.
- Keep access-token lifetimes appropriately limited.
- Use refresh-token rotation and blacklisting where configured and required.
- Avoid logging passwords, access tokens, refresh tokens, or Authorization
  headers.

Registration must validate email addresses and passwords. Passwords must
be handled using Django's password hashing functions.

An email verification flag does not itself prove that email verification
has occurred. The verification workflow must be implemented and tested
before unverified accounts are treated as verified.

## 3. Authorization and Ownership

Authentication establishes a user's identity. Authorization determines
which resources that user may access.

Every private resource must be checked against the authenticated owner.

Examples include:

- Conversations and messages.
- Uploaded knowledge documents and their chunks.
- File attachments.
- Message feedback.
- Image-generation requests and generated images.
- Account preferences and profile information.

Recommended rules:

1. Filter private querysets by the authenticated user.
2. Verify ownership before retrieving, updating, or deleting a resource.
3. Derive the owner from the authenticated request, not client input.
4. Do not trust resource IDs as proof of authorization.
5. Return appropriate 403 or 404 responses for unauthorized access.
6. Test attempts to access another user's data.

A foreign key relationship does not automatically enforce API ownership.
Views, serializers, and services must apply the necessary checks.

## 4. Secret Management

API keys, database passwords, signing secrets, and other credentials must
not be hardcoded in source code.

Use environment variables or a managed secrets service.

Examples of secret-bearing configuration include:

- `DJANGO_SECRET_KEY`
- `OPENAI_API_KEY`
- Database credentials
- Other AI provider API keys
- External storage credentials

The `.env` file is for local configuration and must not be committed to
version control.

The `.env.example` file should contain only placeholder values, for example:

    DJANGO_SECRET_KEY=replace-with-a-secure-random-secret
    DJANGO_DEBUG=False
    DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1
    OPENAI_API_KEY=replace-with-your-provider-key

Never put real credentials in `.env.example`.

Before deployment:

- Generate a unique, high-entropy Django secret key.
- Configure production secrets outside source control.
- Restrict access to secrets to the services that need them.
- Rotate credentials that may have been exposed.
- Never return API keys or credential values in API responses.
- Avoid placing credentials in database model configuration fields.

A database field intended to contain an environment variable name should
store the variable name, not the associated secret.

## 5. Django Production Settings

Production deployments must use the production settings module.

Recommended production controls include:

- `DEBUG=False`
- A strong `DJANGO_SECRET_KEY`
- Explicit `ALLOWED_HOSTS`
- HTTPS enforcement where TLS terminates at the application or proxy
- Secure session and CSRF cookies where applicable
- Appropriate HSTS configuration after HTTPS is confirmed
- Correct trusted proxy configuration
- Explicit CORS and CSRF trusted origins
- Secure database connection settings
- Restricted administrative access

Do not enable HSTS preload or long-lived HSTS policies until the domain,
HTTPS configuration, and all relevant subdomains are ready.

Do not use Django's development server as the production application server.

## 6. CORS and CSRF

CORS controls whether browser-based clients may read responses from a
different origin. It is not an authentication or authorization mechanism.

Production CORS configuration must list only the frontend origins that
actually need access.

Avoid enabling unrestricted origins, especially when credentials are allowed.

Configure CSRF protection according to the authentication method. If
cookie-based authentication is used, state-changing requests require
appropriate CSRF controls.

JWT authentication in an Authorization header has different CSRF
characteristics from session or cookie-based authentication. The final
configuration should be tested against the actual frontend architecture.

## 7. File Upload Security

Uploaded files are untrusted input.

Basic filename, extension, reported MIME type, and size checks are useful
but do not prove that the underlying file content is safe.

Required protections include:

- Enforce strict maximum upload sizes.
- Allow only explicitly supported file types.
- Inspect actual file contents using appropriate parsers.
- Reject malformed or unexpected file formats.
- Use server-controlled storage names.
- Prevent path traversal and directory escape.
- Keep private uploads outside publicly executable directories.
- Restrict file downloads according to resource ownership.
- Apply processing time and memory limits.
- Clean up failed or abandoned uploads.
- Scan files for malware when the deployment's threat model requires it.

Do not trust a filename extension or user-provided Content-Type header as
the sole indication of file type.

For PDF and DOCX parsing, use maintained libraries and catch parsing failures
without disclosing internal exception details to the client.

## 8. URL Ingestion and SSRF Protection

Knowledge documents may eventually be imported from URLs.

Fetching arbitrary user-supplied URLs can create server-side request forgery
(SSRF) vulnerabilities.

Before URL ingestion is enabled, implement controls such as:

- Allow only permitted URL schemes, normally HTTPS.
- Reject localhost, private, link-local, and reserved IP addresses.
- Resolve and validate destination addresses.
- Revalidate redirect destinations or disable redirects.
- Prevent access to cloud instance metadata endpoints.
- Apply strict connection and read timeouts.
- Limit response sizes and download duration.
- Do not forward internal credentials to external destinations.
- Apply outbound network restrictions at the infrastructure level.

DNS resolution and redirects must be considered when validating destinations.
A one-time hostname check is not sufficient for a robust SSRF defense.

URL ingestion must remain disabled until these protections are implemented
and tested.

## 9. AI Provider Security

AI requests may send user prompts or document excerpts to external providers.

Before data is sent to a provider:

- Identify what user information will be transmitted.
- Avoid sending unnecessary personal or confidential information.
- Keep provider credentials server-side.
- Set request timeouts and bounded retry policies.
- Validate provider responses before storing or returning them.
- Handle rate limits and provider failures safely.
- Avoid logging raw prompts and responses unless there is a justified,
  documented need and suitable access controls.
- Apply retention policies to saved conversation and request data.

Provider privacy, retention, and data-processing terms must be reviewed
before sending sensitive production data to that provider.

AI-generated content should be treated as untrusted output.

The application must not allow model output alone to authorize privileged
actions, execute arbitrary code, or bypass the normal permission system.

## 10. Prompt Injection and Tool Safety

User prompts, uploaded documents, retrieved chunks, and web content may
contain malicious instructions.

Mitigations include:

- Treat retrieved documents and web content as untrusted data.
- Separate system instructions from user-provided content.
- Restrict tools to explicit, narrowly defined permissions.
- Validate tool arguments before execution.
- Require normal application authorization for sensitive actions.
- Do not place secrets in prompts merely to make them accessible to a model.
- Do not execute generated shell commands or database operations without
  a controlled, separately authorized mechanism.

Prompt instructions are not a substitute for server-side authorization.

## 11. Knowledge Retrieval Security

Every retrieval query must be scoped to documents the authenticated user
is authorized to access.

Do not retrieve chunks across users' private documents and then rely on
the frontend to hide unauthorized results.

Recommended controls include:

- Filter retrieval queries by document ownership.
- Apply the same restriction when reading document metadata.
- Validate stored embedding dimensions and numeric values.
- Treat retrieved content as untrusted.
- Prevent cross-user cache leakage.
- Delete associated chunks when a document is deleted.
- Define retention and deletion procedures for document files and embeddings.

Embedding vectors should be treated as potentially sensitive derived data
rather than automatically anonymous information.

## 12. Image Generation and Storage

Generated image content and provider responses must be validated before
storage.

Required controls include:

- Limit the requested number of images.
- Validate image bytes and actual image format.
- Check image dimensions and total pixel count.
- Apply maximum output file sizes.
- Use server-generated storage names.
- Avoid fetching arbitrary URLs returned by a provider.
- Store provider credentials outside database records.
- Ensure image history and downloads are owner-scoped.
- Clean up partially stored images after failed operations.

A public image flag must not bypass normal authorization unless a separate,
deliberately designed public-sharing feature allows that behavior.

Storage backends and cleanup procedures must be tested independently of
database transaction handling.

## 13. Rate Limiting and Resource Controls

Authentication endpoints and resource-intensive AI features should have
appropriate abuse controls.

Recommended targets include:

- Registration and login attempts.
- Password or email verification workflows.
- Assistant chat requests.
- Image-generation requests.
- Document uploads and processing.
- Embedding generation and retrieval.
- Any web-search or external-fetching functionality.

Apply per-user and, where appropriate, per-IP limits.

Also consider:

- Maximum prompt and upload sizes.
- Provider concurrency limits.
- Request timeouts.
- Bounded retries.
- Background task queues for long-running jobs.
- Database query limits and pagination.
- Provider quota monitoring.

DRF throttling provides a useful application-level control but should not
be treated as the only defense against denial-of-service attacks.

## 14. Logging and Error Handling

Logs should help diagnose operational problems without exposing sensitive
data.

Avoid recording:

- Passwords or password-reset tokens.
- JWT access and refresh tokens.
- API keys and database credentials.
- Full Authorization headers.
- Raw exception messages from external providers when they may contain
  sensitive values.
- Private document contents unless explicitly justified.

Prefer safe identifiers such as request UUIDs, error codes, event names,
and processing durations.

Unexpected API errors must not expose internal stack traces, file paths,
database credentials, or provider secrets in production responses.

Ensure log access, storage, and retention are controlled.

## 15. Database and Data Retention

Use least-privilege database accounts.

Production databases should have:

- Strong credentials.
- Network access restrictions.
- Encrypted connections where supported and required.
- Regular backups.
- Tested restoration procedures.
- Restricted administrative access.
- Monitored storage and connection usage.

Define retention and deletion policies for:

- User accounts.
- Conversation history.
- Uploaded documents.
- Extracted text and embeddings.
- Generated images.
- Request metadata and diagnostic logs.

Database deletion does not necessarily remove objects from external storage.
File cleanup and related-record deletion must be handled explicitly.

## 16. Dependencies and Supply Chain

Maintain dependency requirements and review updates.

Recommended practices:

- Install packages in an isolated virtual environment.
- Review security updates for dependencies.
- Use reproducible, tested dependency versions for deployment.
- Run dependency vulnerability scans.
- Avoid installing unnecessary packages in production images.
- Do not deploy dependencies before compatibility checks pass.

Requirements files with version ranges do not, by themselves, lock the exact
package versions used in a deployment. Consider a lock file or a tested,
immutable build artifact for reproducible releases.

## 17. Deployment Security

Production deployment should include:

- A dedicated application process and non-root runtime user.
- HTTPS at the public edge.
- Restricted inbound network rules.
- Controlled outbound network access.
- Protected environment variables.
- Secure file and database permissions.
- Health checks and application monitoring.
- A documented update and rollback procedure.
- Tested database migrations.
- Backup and restore procedures.

For container deployments, avoid copying `.env`, local databases, secrets,
or development-only artifacts into container images.

Use separate settings and credentials for development, testing, staging,
and production.

## 18. Security Verification Checklist

Before production release, verify each item:

- [ ] `DEBUG=False` in production.
- [ ] Production secret key is unique and protected.
- [ ] Allowed hosts are explicitly configured.
- [ ] HTTPS and cookie settings are correct.
- [ ] CORS and CSRF origins are restricted appropriately.
- [ ] JWT login, expiry, refresh, and invalid-token handling are tested.
- [ ] Anonymous access is denied for protected endpoints.
- [ ] One user cannot retrieve another user's resources.
- [ ] File content and size validation are tested.
- [ ] URL ingestion is disabled until SSRF protections exist.
- [ ] AI credentials do not appear in API responses or logs.
- [ ] Provider responses and generated image bytes are validated.
- [ ] Rate limits and resource limits are configured.
- [ ] Error responses do not expose internal details.
- [ ] Backups and restoration are tested.
- [ ] Dependency security checks are performed.
- [ ] Migrations are reviewed before deployment.
- [ ] Deletion and storage cleanup behavior is tested.
- [ ] Security tests pass against the intended deployment settings.

## 19. Review and Maintenance

Security is an ongoing process.

Update this document whenever authentication, provider integrations,
file processing, storage, deployment configuration, or data-retention
behavior changes.

Controls listed in this document should be considered requirements until
they have been implemented and verified in the actual application.

