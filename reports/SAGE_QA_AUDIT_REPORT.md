# SAGE Application Audit, Testing and QA Report

**Audit date:** 2026-10-28  
**Audit status:** Partial. Automated tests and targeted static/manual checks are complete; the external-provider and full browser workflow matrix remains untested.  
**Change policy:** No application code was changed as part of this audit. This report is the only audit deliverable.

## 1. Executive summary

The project is a FastAPI application with a browser-based JavaScript frontend, SQLAlchemy persistence, a tool-using OpenRouter agent, and a JSON-backed document vector store. The existing suite collected and ran **88 tests: 88 passed, 0 failed, 0 skipped**, with 172 deprecation warnings. All four frontend JavaScript files passed Node syntax checks, and `git diff --check` exited successfully.

The audit found one high-priority security risk: the LLM tool registry exposes file-reading, PDF-reading, and CSV-analysis functions that constrain paths to the shared `DATA_DIR`, but do not constrain them to the authenticated user's directory. A disposable isolated fixture confirmed that `read_file` can return a file placed under a different simulated user's directory. The same missing owner boundary is visible in the PDF and CSV tools. This is a potential cross-account disclosure through LLM tool calls; it was not exercised against any real user file.

An operational issue was also confirmed: `/api/health` is in the router to which the application applies `require_authenticated`, so an unauthenticated request receives HTTP 401. This prevents unauthenticated infrastructure health probes from using the endpoint.

The audit did not contact the configured LLM provider or run the full UI workflow matrix. Browser visual checks were limited to math rendering and responsive equation overflow rather than every navigation, form, modal, and theme interaction. Those areas are listed as not tested below.

## 2. Project architecture and feature inventory

### Frontend

- `frontend/login.html` and `frontend/auth.js`: sign-in and account creation UI and requests.
- `frontend/index.html`: protected application shell and script/style loading.
- `frontend/app.js`: chat messages, Markdown conversion, conversation navigation/history, and workspace views.
- `frontend/upgrades.js`: additional workspace features, including notes, plans, settings, and upload-oriented UI.
- `frontend/styles.css`, `frontend/upgrades.css`: base and extended layouts/themes.
- `frontend/auth-session.js`: session-aware fetch behavior, logout, and page restoration.
- `frontend/math-formatting.css`: message typography, tables, code, and responsive equation styling.
- Static logo asset under `frontend/public/assets/`.
- No frontend `package.json`, JavaScript test runner, linter, or build script was found. `package-lock.json` contains no installed packages.

### Backend

- `app/main.py`: FastAPI application, startup, private response-cache headers, frontend shell, routers, static files, and global authentication dependency for the main API router.
- `app/api/auth.py`, `auth_context.py`, `dependencies.py`, `schemas.py`, `routes.py`: authentication, request validation, per-request user context, agent dependency, and API routes.
- `app/agent/`: planner, registry, executor, and `VDSSAgent` orchestration.
- `app/llm/`: OpenRouter client and model configuration.
- `app/prompts/`: system and tool prompts.
- `app/database/`: SQLAlchemy models, migrations/startup initialization, and CRUD functions.
- `app/services/`: document, study-plan, study, and user services.
- `app/memory/`: short-term, long-term, and manager layers.
- `app/rag/`: document loading, chunking, vector storage, and retrieval.
- `app/tools/`: calculator, calendar, code analysis, date/time, embeddings, file/PDF readers, marks, memory, notes, CSV analysis, RAG, reminders, study planning, quizzes, and web search.

### Database and persisted data

The SQLAlchemy model classes are `User`, `AuthSession`, `LoginAttempt`, `Note`, `Mark`, `StudyPlan`, `Memory`, `Reminder`, `CalendarEvent`, `Conversation`, and `Message`. Most user records have a `user_id`; messages are scoped through their conversation. The vector store is a JSON file rather than a relational table.

`create_tables()` performs additive schema changes and assigns unowned legacy rows to owner ID 1. It also calls `assign_legacy_owner(1)` for vector documents missing an owner. Migration tests cover representative legacy rows and study-plan/note schema changes.

### APIs and templates

- Auth: register, login, session status, logout.
- Main API: health, chat, chat-with-attachment, conversations, notes and Notes PDFs, study plans/statistics/preview/bulk generation, memories, documents, document open/delete, and chat-attachment deletion.
- Server-side chat templates: General Assistant (default), Study Tutor, Coding Assistant, and Document Assistant.
- Workspace prompt templates are also rendered in the frontend. The default General Assistant does not add a template-specific system instruction; the other three do.
- Chat requests store conversations and messages, use recent context, and make non-streaming completion calls. The client timeout is 60 seconds, retries are disabled, and the agent has an eight-iteration tool limit.

## 3. Environment, commands, and evidence

### Environment discovered

- Windows workspace: `C:\Users\Gokul\OneDrive\Desktop\Agent`.
- Project virtual environment: `.venv`; interpreter reports Python 3.14.
- No root `pytest.ini`, `pyproject.toml`, or `package.json` was found.
- No project frontend test/build/lint command is configured.
- The configured provider uses the OpenAI-compatible OpenRouter client. No provider request was made during this audit.

### Commands actually run

| Command/check | Result |
|---|---|
| `.venv\Scripts\python.exe -m pytest --collect-only -q` | 88 tests collected |
| `.venv\Scripts\python.exe -m pytest -q` | 88 passed, 0 failed, 0 skipped; 172 warnings; 25.94 seconds |
| `node --check frontend/app.js` | Passed |
| `node --check frontend/auth-session.js` | Passed |
| `node --check frontend/auth.js` | Passed |
| `node --check frontend/upgrades.js` | Passed |
| `git diff --check` | Passed (exit 0) |
| Isolated `read_file` ownership probe | Returned contents of a disposable file under simulated `data/documents/user_987/` |
| Unauthenticated `GET /api/health` via FastAPI TestClient | HTTP 401, `{"detail":"Authentication required."}` |

The isolated file-reader probe redirected the module's data root to a temporary directory, created a disposable fixture, and removed the temporary directory automatically. It did not use any existing user's document.

### Audit-side database startup side effect

The TestClient health probe was run with the app lifespan enabled before the configured database had been redirected to an isolated database. Consequently, application startup ran `create_tables()` against the configured `data/vdss.db`. The file existed afterward and its observed modification time was `2026-10-28 11:05:47`; its pre-probe modification time was not recorded, so the exact schema/data delta cannot be established. The inspected startup routine applies schema/ownership migrations and does not delete rows. No attempt was made to roll back or rewrite the database because that could risk existing data. The vector file's observed modification time was earlier than the probe (`2026-10-23 19:51:33`). This was an audit-process isolation error and is explicitly disclosed.

## 4. Automated test results

All collected tests passed. The suite files include:

- `tests/test_agent.py`
- `tests/test_agent_features.py`
- `tests/test_auth.py`
- `tests/test_chat_templates.py`
- `tests/test_database.py`
- `tests/test_memory.py`
- `tests/test_note_pdf.py`
- `tests/test_rag.py`
- `tests/test_study_plan.py`

`tests/test_calculator.py` and `tests/test_tools.py` are empty (0 bytes) and contributed no tests. Calculator and tool behavior is partially covered by agent-feature tests, but these empty files indicate missing dedicated modules.

Warnings were primarily `datetime.utcnow()` and SQLite datetime adapter deprecations, plus Starlette's warning about use of `httpx` with `TestClient`. They did not fail this run.

## 5. Module-by-module test matrix

Statuses refer to actual automated tests or the explicitly described manual/static check. “Not tested” does not imply the feature is broken.

| Test ID | Feature | Scenario | Expected result | Actual result | Status | Evidence |
|---|---|---|---|---|---|---|
| AUTH-01 | Registration | Valid account and password storage | New account; password hashed | Passed | PASS | `test_registration_hashes_password_and_persistent_cookie_survives_new_client` |
| AUTH-02 | Registration | Duplicate username | Clear conflict response | Passed | PASS | Same auth test; duplicate response asserted |
| AUTH-03 | Login | Invalid credentials and throttling | Reject invalid login; rate-limit repeated failures | Passed | PASS | `test_failed_login_rate_limit_logout_and_session_expiry` |
| AUTH-04 | Sessions | Restoration, expiry, logout revocation | Restore valid session; reject expired/revoked session | Passed | PASS | Auth session test |
| AUTH-05 | Auth boundaries | Unauthenticated APIs, cross-origin writes, private shell | Reject unauthorized/cross-origin requests; gate shell | Passed | PASS | `test_unauthenticated_private_api_is_rejected`, `test_cross_origin_mutations_are_rejected`, `test_private_application_shell_requires_a_valid_session` |
| AUTH-06 | Ownership | Guessed IDs and user-owned documents/Notes PDFs | Prevent cross-user access | Passed for covered API cases | PASS | `test_user_data_and_guessed_ids_are_isolated`, `test_uploaded_documents_and_note_pdfs_are_owned_by_their_creator` |
| AUTH-07 | Legacy migration | Existing rows and unowned vectors | Preserve rows and isolate under legacy owner | Passed for test fixtures | PASS | `test_legacy_rows_migrate_to_unavailable_legacy_owner`, `test_legacy_vector_documents_are_not_visible_to_new_users` |
| CHAT-01 | API health | Request `/api/health` without a session | Health result available to unauthenticated probe if intended as liveness endpoint | Returns 401 due to router-level auth | FAIL | Isolated TestClient request; `app/main.py` applies `require_authenticated` to the routes router |
| CHAT-02 | Chat API | No configured LLM, provider timeout/failure handling | Controlled fallback/error without leaking exception details | Covered paths passed | PASS | `test_chat_without_llm_key_returns_controlled_response`, `test_agent_handles_llm_timeout_gracefully`, `test_chat_agent_failure_returns_friendly_error_without_exception_details` |
| CHAT-03 | Chat validation | Blank and invalid IDs | Reject invalid request | Passed | PASS | `test_chat_rejects_nonpositive_conversation_ids`, `test_chat_and_note_requests_reject_blank_text` |
| CHAT-04 | Context/history | Multi-turn follow-up, switch chats, refresh persistence | Correct history/context after navigation/reload | Not exercised end-to-end in browser | NOT TESTED | API and CRUD code inspected; no full browser scenario run |
| CHAT-05 | Duplicate actions/loading | Rapid repeated send, stop, timeout UI recovery | Avoid duplicate writes and recover UI state | Not stress-tested | NOT TESTED | Frontend code inspected only |
| CHAT-06 | Response formatting | Markdown/LaTeX, malformed input, sanitization | Visually rendered equations; unsafe HTML remains escaped | Focused browser check performed previously in this conversation: rendered fractions/matrices and checked visible math and untrusted HTML | PASS (focused) | Browser evaluation confirmed KaTeX DOM/visibility and no injected `script`/event-handler nodes; not part of the 88 Python tests |
| TPL-01 | Templates | Persist default/selected template, existing chat behavior | Save selected template and retain existing template | Passed | PASS | `test_new_chat_persists_template_and_existing_conversation_keeps_it`, `test_conversation_create_api_supports_templates_and_default`, `test_selected_template_is_saved_for_new_chat`, `test_attachment_created_conversation_persists_selected_template` |
| TPL-02 | Templates | Actual instructions passed into agent | Template-specific instructions reach agent request | Passed | PASS | `test_templates_change_agent_instructions` |
| TPL-03 | Document Assistant | No selected source and unsupported evidence handling | Avoid unsupported claims | Static path inspected; no live provider call | NOT TESTED | `VDSSAgent.run` contains explicit no-source response; provider behavior not exercised |
| TPL-04 | Template gallery UI | Placement, selection UX, mobile rendering | Gallery in intended location and usable | Not retested during this audit | NOT TESTED | Frontend source inspected; no broad browser workflow |
| NOTE-01 | Text notes | Create, edit, search, delete | Persist and return scoped note changes | Passed | PASS | `test_notes_create_edit_search_and_delete_use_existing_api` |
| NOTE-02 | Notes PDFs | Valid upload, list separation, view/follow-up, delete cleanup | Persist PDF metadata/file and keep separate from normal documents | Passed | PASS | `test_note_pdf_upload_list_and_view_on_followup_request`, `test_note_pdfs_have_a_separate_uploads_list`, `test_note_pdf_and_note_deletion_clean_only_their_attachment` |
| NOTE-03 | Notes PDFs | Empty, malformed, encrypted files | Reject without leaving orphan files | Passed | PASS | Parameterized cases in `tests/test_note_pdf.py` |
| NOTE-04 | Notes persistence | Backend restart and real filesystem recovery | Reopen saved note/PDF after process restart | Not tested | NOT TESTED | Test fixtures use temporary database/files; no restart test |
| DOC-01 | Normal uploads | Ingest supported file, chunk/embed/index | File becomes retrievable and listed | Passed in mocked/unit paths | PASS | `test_ingestion_uses_existing_loader_chunker_and_vector_store`, `test_existing_docx_loader_extracts_paragraph_text`, PDF page/chunk tests |
| DOC-02 | RAG | Selected filename/page filtering and citations | Restrict retrieval and retain page labels | Passed | PASS | `test_retriever_limits_results_to_selected_filename`, `test_retriever_uses_page_filter_and_exact_program_text`, `test_selected_document_llm_receives_page_labeled_evidence` |
| DOC-03 | RAG | Retrieval miss and provider failure | Avoid unsupported absence claims; provide evidence fallback | Passed | PASS | `test_document_retrieval_miss_does_not_claim_content_is_absent`, `test_selected_document_llm_failure_returns_retrieved_evidence` |
| DOC-04 | Upload lifecycle | Delete, failed replacement rollback, selected attachment reuse | Remove only target document and restore on failure | Passed | PASS | `test_document_upload_list_failure_and_individual_delete`, `test_failed_document_replacement_restores_file_and_index`, `test_chat_attachment_uses_existing_conversation_and_is_reused` |
| DOC-05 | Upload inputs | File size limit, encrypted/scanned/empty PDFs, duplicate names | Validate limits and unsupported PDFs | Some malformed/encrypted/unreadable cases passed; broad size/duplicate matrix not fully exercised | BLOCKED | `test_pdf_reader_reports_unreadable_pdf_types` and note-PDF invalid-input tests; no complete upload matrix |
| PLAN-01 | Study plans | CRUD, ownership, statistics/date categories | Persist scoped plan changes and accurate categories | Passed | PASS | `tests/test_study_plan.py` CRUD/statistics tests |
| PLAN-02 | Plan generation | Preview, bulk create, duplicate prevention, schedule bounds | Generate bounded schedule without duplicate tasks | Passed | PASS | `test_study_plan_preview_and_bulk_save_prevent_duplicates`, schedule parsing/bounds tests |
| MEM-01 | Short-term memory | Limits and invalid limits | Keep bounded recent context | Passed | PASS | Three `tests/test_memory.py` tests |
| MEM-02 | Long-term memory API/tool | CRUD and user isolation | Store and retrieve per-user memory | API/ownership paths not comprehensively integration-tested | NOT TESTED | `tests/test_auth.py` includes broad isolation coverage; no dedicated full memory CRUD workflow |
| TOOL-01 | Calculator/tool framework | Calculator limits, required arguments, tool registry and failures | Reject invalid calls safely | Covered paths passed | PASS | Agent-feature tests for deterministic calculator, exponent/non-finite limits, registry and executor |
| TOOL-02 | Quiz, marks, calendar, reminders | CRUD and invalid input/persistence | Correct owner-scoped operations | No dedicated end-to-end module test matrix | NOT TESTED | Tool definitions and registry inspected; no paid/external calls |
| TOOL-03 | Web search | External search result parsing and failure recovery | Return bounded results or useful error | Not executed (external network dependency) | NOT TESTED | Static inspection only |
| UI-01 | Frontend JavaScript | Parse all scripts | No syntax errors | All four scripts passed | PASS | Node `--check` commands above |
| UI-02 | Navigation/forms/dialogs/themes | Browser interaction and accessibility | Controls work at desktop/mobile in both themes | Not comprehensively tested in this audit | NOT TESTED | Source inspected; no full interaction suite |
| UI-03 | Mobile overflow | Long equations/tables/code | Contain overflow without page-wide horizontal scroll | Focused prior browser check found a 390px viewport retained 390px document width; equation container scrolls internally | PASS (focused) | Browser measurement in preceding interaction |
| API-01 | Request validation | Missing/blank/invalid values | Consistent validation errors | Several chat/note/study plan cases pass | PASS (partial) | Schema validation tests listed above |
| API-02 | API-wide fuzzing | Missing fields, malformed bodies, rate limits, large payloads on every endpoint | Stable error contract | Not exhaustively tested | NOT TESTED | No API fuzz/load suite configured |
| PERF-01 | Runtime performance | Representative latency, concurrency, memory | Record measured baseline | No performance benchmark run | NOT TESTED | Pytest duration is not treated as application performance |

## 6. Chat and template behavior

The frontend posts complete chat requests; the API does not expose a streaming response. The route stores user and assistant messages, loads a bounded recent history for context, and passes the conversation's stored template to `VDSSAgent`. The agent adds the Study Tutor, Coding Assistant, or Document Assistant instruction when selected; General Assistant uses the base system prompt. Tests verify template persistence and prompt changes.

No live OpenRouter calls were made, so answer quality, real provider latency, provider rate-limit behavior, actual tool selection, citations produced by the model, and long-running browser recovery remain unverified. Fallback and timeout branches are covered with tests/mocks. The frontend Markdown/math renderer received a focused visual/browser check in the immediately preceding task, but all requested conversation scenarios were not re-run as a complete suite.

## 7. Notes PDF and normal upload separation

The API defines a distinct `/notes/pdfs` listing and note-associated PDF routes. Tests cover a successful PDF attachment, the separate listing, viewing, invalid/empty/encrypted PDF rejection, and targeted cleanup. Normal document upload and retrieval have separate `/documents` routes and user-scoped document directories; RAG tests cover filename filtering, page labels, replacement rollback, and deletion. Full production restart durability, every supported file format, large uploads, multiple duplicate filenames, and OCR for scanned PDFs were not all exercised. The PDF reader explicitly reports that scanned PDFs have no selectable text; OCR is not available in the inspected implementation.

## 8. Authentication and data-isolation results

The existing automated tests cover registration/password hashing, duplicate usernames, login failure/rate limiting, session persistence/expiration/logout, secure-cookie behavior in production mode, unauthorized API access, CSRF-origin rejection, cross-user guessed-ID isolation, file/Notes PDF ownership, and legacy-row migration behavior.

Those tests pass for their fixtures. The isolated file-tool probe demonstrates a separate ownership boundary that those API-focused tests do not cover: the LLM-facing `read_file`, `read_pdf`, and `analyze_csv` functions accept a path anywhere under `DATA_DIR`. Their `relative_to(DATA_DIR)` checks establish a project-root boundary, not a user boundary. Their registry definitions expose path arguments, and the agent offers registered tools to the model when a plan requires tools. `read_file` returned the content of a simulated other-user fixture. This is **not** a proof that real user data was accessed; it is a reproducible ownership-control gap in the tool layer.

## 9. UI/UX and responsive testing

All frontend JavaScript parses under Node. Source inspection confirms theme state, workspace navigation, modal markup, loading indicators, and mobile layouts exist. Focused browser verification from the preceding response-formatting task confirmed visible KaTeX output, restored-history math, dark-mode math color, and internal scrolling for a long display equation at a narrow viewport.

The broad audit did not re-run every browser interaction or screen size. Keyboard-only operation, screen-reader announcements, all forms and dialogs, task UX, PDF viewing on mobile, network failure messaging, and all page-wide overflow combinations are therefore **not tested**.

## 10. Bugs and prioritized findings

### P1 — LLM tools lack per-user file ownership checks

- **Evidence:** `app/tools/file_reader.py:22-31` restricts paths to `DATA_DIR` but does not check the authenticated owner. Similar root-only checks appear in `app/tools/pdf_reader.py:12-18` and `app/tools/python_analysis.py:13-25`.
- **Reachability:** the tools are registered in `app/agent/registry.py:126`, `:139`, and `:297`. `app/agent/agent.py:126` supplies registered tools to the LLM when the planner requires tools.
- **Reproduction:** a disposable file placed under a simulated `DATA_DIR/documents/user_987/` directory was returned by `read_file` when called with its path.
- **Impact:** an authenticated user's prompt/tool-call flow may disclose another user's `.txt`, `.md`, `.csv`, `.json`, `.py`, `.js`, `.html`, or `.css` file content if the model invokes the path-based tool; PDF and CSV tools have analogous missing owner scoping.
- **Confidence:** High for the missing boundary and the isolated `read_file` behavior; real-account exposure was not attempted.
- **Recommended priority:** P1. Enforce owner-scoped roots or pass/verify current user ownership at every file-tool read before treating multi-user file isolation as complete.

### P2 — `/api/health` requires authentication

- **Evidence:** `app/api/routes.py:126` defines the endpoint in the main router; `app/main.py:86` attaches `Depends(require_authenticated)` to that whole router.
- **Reproduction:** unauthenticated TestClient `GET /api/health` returned HTTP 401 with `Authentication required.`
- **Impact:** a load balancer or deployment health probe without a session cannot use this endpoint to check readiness/liveness. This does not expose private data; it is an operational availability/monitoring concern.
- **Confidence:** High.
- **Recommended priority:** P2. Decide whether this endpoint is intended to be public liveness-only or intentionally private, then align deployment probes and route dependencies.

### P0 findings

None established by the checks run.

## 11. Security and data-loss risks

- **Confirmed risk:** the path-based LLM file tools are not scoped to the authenticated user's document root (P1 above).
- **Database migration:** startup migrations assign null/unowned rows to legacy owner ID 1 and add columns/indexes; migration tests passed for representative fixtures. This audit's startup health probe touched the configured local database as disclosed above; no intentional deletion was performed.
- **Session defenses:** session tokens are stored hashed server-side; cookie is HttpOnly, SameSite=Lax, and Secure in production mode; logout revocation and expiry have tests. Origin/Fetch Metadata checks are present for mutating requests.
- **HTML rendering:** frontend code escapes AI content before building message markup; the focused browser test found no injected `script` or event-handler elements. This is not a full security assessment of every dynamic workspace HTML template.
- **Secrets:** the audit did not read or reproduce `.env` values. No API key, password, or cookie value is included in this report.
- **Not assessed:** production reverse-proxy/TLS configuration, secret rotation, OS file permissions, database backup/recovery, dependency vulnerability scanning, and deployment-specific CORS/CSP headers.

## 12. Performance and reliability

No representative request latency, concurrency, throughput, memory, or resource measurements were taken. The 25.94-second pytest duration is a test-suite runtime, not a production performance benchmark. The LLM client has a 60-second timeout and no retries; actual provider failure modes were mocked or inspected rather than contacted. No uncontrolled paid provider requests were made.

## 13. Missing coverage and remaining work

1. Add isolated tests that exercise every LLM-exposed file tool under multiple authenticated owner contexts, including file, PDF, and CSV reads.
2. Decide and test expected unauthenticated behavior for `/api/health`.
3. Add a frontend automation harness and tests for registration/login/logout, chat/history/template flows, notes/PDFs, uploads, plans, settings, themes, and error states.
4. Add direct tests for quiz, marks, calendar, reminder, and long-term memory CRUD/error behavior.
5. Add persistence/restart tests for the database, Notes PDFs, normal uploads, and vector index.
6. Exercise actual supported upload size limits, scanned/encrypted/malformed files, duplicate names, and all file formats using temporary directories.
7. Add non-production load/latency checks and broader API validation tests.
8. Reconcile the startup side effect: compare the current local schema/data state with a known backup or migration record before any attempt to restore or alter the database.

## 14. Recommended fix and QA order

1. **P1:** close file-tool ownership scope for all file readers/analysers; add isolated cross-owner regression tests before release.
2. **P2:** set the health-check authentication contract and verify the configured infrastructure probe.
3. Add frontend automation for the highest-risk paths (auth, conversation ownership, selected document, Notes PDF vs. normal uploads).
4. Complete direct CRUD tests for lower-level tools and persistence after backend restart.
5. Add performance and deployment checks only after the security and frontend harness are in place.

## 15. Working tree and audit limits

Before creating this report, the worktree already contained changes in `app/prompts/system_prompt.py`, `frontend/app.js`, `frontend/index.html`, `tests/test_auth.py`, and an untracked `frontend/math-formatting.css`. These were preserved and not altered by the audit. The report file is the only file created for this audit.

This report is evidence-based but not a claim that every UI workflow, provider behavior, file format, deployment topology, or performance scenario has been exhaustively tested. The outstanding scenarios above remain open.

## 16. Remediation follow-up — 2026-10-28

The two findings above have now been addressed in the working tree:

- Registered `read_file`, `read_pdf`, and `analyze_csv` tools resolve requested paths against the server-derived user's document directory. Resolved paths outside that directory are rejected; traversal and symlink/junction escapes are rejected as well. The legacy owner-1 documents root is prevented from traversing into `user_<id>` directories.
- The registered `ingest_project_document` tool now resolves filenames through the same owner check, and `search_knowledge` always uses the authenticated context for vector-store ownership. Neither accepts an LLM-supplied owner ID.
- Database-backed agent tools likewise no longer declare or accept `user_id` as an LLM argument; they scope CRUD calls from the server-side authenticated context.
- Trusted internal document-ingestion helpers still support files stored under the shared data directory so that app-managed chat attachments and uploads continue to parse. These helpers are not registered as AI tools; the registered entry points enforce user ownership first.
- No deployment or infrastructure health-probe configuration was found in the repository. `/api/health` is now a minimal unauthenticated liveness endpoint returning only `{"status":"ok"}`. The private API router remains protected by `require_authenticated`.

Regression tests create isolated temporary user directories and PDFs/CSVs/text files. They demonstrate that one user cannot read another user's files through each registered reader, that same-owner reads succeed, that traversal and Windows directory-junction escapes are rejected, and that ingestion/search/database tools do not trust LLM-supplied owner identifiers. The health test verifies both unauthenticated liveness and continued protection of `/api/conversations`.

Validation after these changes: focused ownership/health tests passed (**9 passed**). The full suite passed (**96 passed, 0 failed, 0 skipped; 174 warnings; 35.66 seconds**), and final `git diff --check` passed. Test runs used a disposable SQLite database under the system temporary directory; the configured `data/vdss.db` was not used by this remediation validation. The warnings are the existing `datetime.utcnow()`, SQLite adapter, and Starlette/httpx deprecations noted above.
