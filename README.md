# Agentic RAG + Web Search

This project is being built in small, testable phases. It will become a secure
application where users can chat with their permitted books, search the web
when needed, and use tools such as a calculator. The current implementation
contains Phases 1 through 18 plus end-to-end runtime integration.

## What is available now

- FastAPI backend with a health endpoint
- Streamlit frontend that checks backend connectivity
- SQLite user database
- Secure Argon2 password hashing
- JWT access and refresh tokens
- Account registration, login, token refresh, and current-user API routes
- Backend-only role and document-access authorization rules
- PDF extraction, configurable chunking, and secure chunk metadata generation
- ChromaDB dense-vector storage with pre-retrieval access filtering
- BM25 sparse keyword search with separate per-user authorized corpora
- Hybrid dense + sparse retrieval with reciprocal rank fusion
- Cross-encoder reranking over authorized hybrid candidates
- Grounded RAG answer generation with source/page citations
- Safe calculator tool for arithmetic and percentage calculations
- Configurable Tavily/Serper web-search tool with validated source URLs
- LangGraph supervisor with bounded RAG, web, calculator, and direct-response routing
- Bounded sequential RAG/web/calculator delegation with synthesis of worker results
- Authenticated chat wired through the LangGraph supervisor, delegated workers,
  authorized retrieval, web search, calculator, Groq generation, and source return
- Persistent conversations and ordered messages with owner-scoped authorization
- Persisted assistant-agent and source metadata so citations survive conversation reloads
- Authenticated Groq token streaming through FastAPI SSE and a Streamlit client
- Docker images and Compose configuration for the backend and frontend, with
  persistent local application data
- Streamlit login/registration, user-scoped conversation history, chat, agent
  status, source panel, and logout
- Security regression coverage for JWT validation, authorization boundaries,
  prompt injection handling, calculator misuse, and API-key leakage
- Automated tests for health, authentication, RBAC, retrieval, tools, and
  supervisor/delegation/streaming workflows

The Streamlit interface supports account login/registration, conversation
history, streaming chat, agent indication, source display, and logout.
Docker Compose can run both services together; see Phase 18 below.
For the local, non-Docker test walkthrough and example Streamlit questions,
see [TEST_COMMANDS.md](./TEST_COMMANDS.md).

## Project structure

```text
backend/
  app/
    agents/
      supervisor.py          # Typed LangGraph routing and worker dispatch
      delegation.py          # Bounded multi-agent workflows and synthesis
      runtime.py             # Production worker bindings for the chat endpoint
    api/
      auth.py                # Authentication HTTP endpoints
      chat.py                # Authenticated server-sent-event chat endpoint
      conversations.py       # Authenticated conversation history endpoints
    auth/                    # Password, JWT, and authorization logic
    conversations/
      service.py             # Owner-scoped conversation persistence
    llm/
      groq.py                # Groq streaming provider adapter
    config.py                # Settings read from .env
    database.py              # SQLite connection and request sessions
    main.py                  # FastAPI app and health endpoint
    models.py                # User and role database models
    rag/
      bm25.py                # Access-filtered sparse retrieval
      chroma.py              # Access-filtered dense retrieval
      hybrid.py              # Reciprocal-rank fusion of authorized results
      reranking.py           # Cross-encoder reranking
      generation.py          # Grounded answers and source citations
      ingestion.py           # PDF extraction and chunk metadata
frontend/
  app.py                     # Login, conversation history, and streaming chat UI
  api_client.py              # Authenticated FastAPI client
scripts/
  index_bm25.py              # Builds the access-filtered BM25 index
  index_chunks.py            # Builds the Chroma dense-vector index
  manage_user.py             # Creates or updates a local user/admin account
  reset_password.py          # Interactively resets a local account password
  seed_users.py              # Creates initial accounts safely
backend/app/tools/
  calculator.py              # Safe arithmetic tool
  web_search.py              # Tavily/Serper web-search integration
tests/                       # Automated tests
data/                        # Reserved for PDFs and later retrieval indexes
```

## Setup and run

For a copy-paste-oriented list of project commands, see
[COMMANDS.md](./COMMANDS.md).
For a local, step-by-step test walkthrough with sample questions for the
Streamlit interface, see [TEST_COMMANDS.md](./TEST_COMMANDS.md).
For a shorter scenario with login guidance and questions to try in order, see
[SCENARIO.md](./SCENARIO.md). It intentionally contains no passwords or API
keys.
For first-time setup from a fresh GitHub ZIP download, follow
[USER_GUIDE.md](./USER_GUIDE.md).

### Step 1: Create a virtual environment

```powershell
python -m venv .venv
& ".\.venv\Scripts\python.exe" -m pip install --upgrade pip
& ".\.venv\Scripts\python.exe" -m pip install -r requirements.txt
```

### Step 2: Create local configuration

Copy the example file and configure `JWT_SECRET_KEY`:

```powershell
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
```

Open `.env` and set `JWT_SECRET_KEY` to a long random value. Do not commit this
file or share this key. Authentication endpoints cannot issue or validate
tokens until it is set. Use `.venv\Scripts\python.exe` for all commands to
ensure they run in the same environment as the installed dependencies. For a
guided local walkthrough and clean-environment recovery steps for native
Python module errors, see
[TEST_COMMANDS.md](./TEST_COMMANDS.md).

### Step 3: Start the backend

Open a terminal in the project root and run:

```powershell
& ".\.venv\Scripts\python.exe" -m uvicorn app.main:app --app-dir backend --reload
```

The API is available at `http://localhost:8000`. Visit
`http://localhost:8000/docs` to use the interactive API documentation.

### Step 4: Start the frontend

Open a second terminal and run:

```powershell
& ".\.venv\Scripts\python.exe" -m streamlit run frontend/app.py
```

Open `http://localhost:8501`. A successful **Backend online** message in the
sidebar confirms that Streamlit can communicate with FastAPI.

### Step 5: Run the tests

```powershell
& ".\.venv\Scripts\python.exe" -m pytest -q
```

All tests should pass before moving to the next phase.

## Phase 1: Application foundation

### Purpose

Provide the smallest working connection between a user interface and a backend.

### What was built

1. A FastAPI application in `backend/app/main.py`.
2. A `GET /api/health` endpoint that reports whether the backend is running.
3. A Streamlit page in `frontend/app.py`.
4. A small API client that asks the backend for its health state.
5. Centralized configuration in `backend/app/config.py`.
6. An `.env.example` file and a `.gitignore` that excludes `.env`.
7. A health endpoint test.

### How it works

```text
Streamlit page -> GET /api/health -> FastAPI response -> Streamlit status message
```


This phase intentionally contains no login, documents, or AI features.

## Phase 2: Authentication

### Purpose

Allow users to create an account and securely prove their identity to the API.

### What was built

1. A SQLite `users` table with a unique username, role, and password hash.
2. Argon2 password hashing through `pwdlib`; plaintext passwords are never
   stored in the database.
3. Short-lived access tokens and longer-lived refresh tokens.
4. Endpoints for registration, login, token refresh, and current-user lookup.
5. A `get_current_user` FastAPI dependency that validates bearer tokens.
6. Tests for the full register -> login -> `/me` -> refresh flow.

### Authentication flow

```text
Register -> password is hashed -> user is stored in SQLite
Login -> password is verified -> access token + refresh token returned
Request to protected API -> Authorization: Bearer <access token>
Backend -> validates token -> loads current user
```

### Authentication API

| Endpoint | Method | What it does |
| --- | --- | --- |
| `/api/auth/register` | POST | Creates a normal user account. |
| `/api/auth/login` | POST | Returns an access token and refresh token. |
| `/api/auth/refresh` | POST | Exchanges a refresh token for a new token pair. |
| `/api/auth/me` | GET | Returns the logged-in user. Requires a bearer access token. |

### Create the initial accounts

The seed script safely creates `admin`, `user1`, and `user2`; passwords must be
supplied by the operator and are not placed in source code:

```powershell
python scripts/seed_users.py --admin-password "use-a-long-password" --user1-password "use-a-long-password" --user2-password "use-a-long-password"
```

If an account already exists, the script leaves it unchanged.

## Phase 3: Role-based access control (RBAC)

### Purpose

Establish the critical security rule for later retrieval: users must never see
content from a book they are not allowed to access.

### What was built

1. Two roles: `admin` and `user`.
2. `require_role(...)`, a reusable dependency for future admin-only API routes.
3. `can_access_document(user, metadata)`, a reusable backend authorization
   function.
4. Tests that prove the document boundary is enforced.

### Document access rule

Each future document or chunk will include metadata like this:

```python
{
    "book_id": "book1",
    "allowed_user_ids": ["user1"]
}
```

The backend uses this rule:

```text
Is the user an admin?
  Yes -> allow access
  No  -> allow only if the user's ID is in allowed_user_ids
          otherwise deny access
```

### Verified security behavior

| User | Book 1 | Book 2 |
| --- | --- | --- |
| `user1` | Allowed | Denied |
| `user2` | Denied | Allowed |
| `admin` | Allowed | Allowed |

The access check fails closed: if access metadata is missing or invalid, a
normal user is denied. This authorization logic is entirely in the backend,
not the Streamlit UI or an LLM.

## Phase 4: PDF ingestion

### Purpose

Prepare the two books for later search without losing the source, page number,
or authorization information needed to protect them.

### What was built

1. A PDF reader that extracts text page by page.
2. Configurable text cleanup and overlapping chunking.
3. Metadata creation for every chunk.
4. A command that resolves allowed usernames to immutable database user IDs.
5. An inspectable JSONL output file for verification before vector indexing is
   added in Phase 5.

### Ingestion flow

```text
PDF -> extract page text -> clean text -> create overlapping chunks
    -> attach page/source/book/access metadata -> JSONL verification artifact
```

Every output chunk contains `book_id`, `book_name`, `owner_user_id`,
`allowed_user_ids`, `source`, `page_number`, and `chunk_id`. The command does
not use usernames directly in the final metadata: it resolves them to database
user IDs so the Phase 3 authorization rule can be used unchanged.

### Ingest a book

First put your files in `data/books/` (for example, `book1.pdf` and
`book2.pdf`) and make sure the initial users have been seeded. Then run:

```powershell
python scripts/ingest_pdf.py data/books/book1.pdf --book-id book1 --book-name "Book 1" --owner-username user1 --allowed-usernames user1
python scripts/ingest_pdf.py data/books/book2.pdf --book-id book2 --book-name "Book 2" --owner-username user2 --allowed-usernames user2
```

The resulting chunks are written to `data/processed/book1.jsonl` and
`data/processed/book2.jsonl`. These local verification files are ignored by
Git. You can tune `CHUNK_SIZE` and `CHUNK_OVERLAP` in `.env`; their defaults are
800 and 100 characters respectively.

### Current ingestion verification

The two PDFs currently in this project have been ingested successfully:

| Source | Chunks | Authorized user |
| --- | ---: | --- |
| `book1.pdf` | 158 | `user1` and `alice` |
| `book2.pdf` | 15 | `user2` only |

The generated metadata was tested against the backend authorization rule:
`user1` and `alice` are denied Book 2, `user2` is denied Book 1, and `admin`
is allowed to access both books.

## Phase 5: ChromaDB and dense retrieval

### Purpose

Store the ingested chunks as semantic vectors so later RAG features can find
relevant information by meaning, while preserving the Phase 3 security rule.

### What was built

1. A persistent ChromaDB collection named `rag_documents`.
2. Configurable local Sentence Transformers embeddings using
   `sentence-transformers/all-MiniLM-L6-v2` by default.
3. A JSONL-to-Chroma indexing command.
4. Dense search that applies the user access filter inside the Chroma query,
   before candidates are returned.
5. Tests proving that an unauthorized book is never part of a normal user's
   dense-search result set.

### Why Chroma stores one record per allowed user

Chroma metadata accepts scalar values, while Phase 4 chunk metadata contains
an `allowed_user_ids` list. During indexing, a chunk is written once per
permitted user with a scalar `allowed_user_id`. A normal-user search sends this
filter directly to Chroma:

```text
User 1 query -> where allowed_user_id = User 1's immutable ID -> Book 1 candidates only
User 2 query -> where allowed_user_id = User 2's immutable ID -> Book 2 candidates only
Admin query  -> full managed corpus
```

This means filtering is not performed after retrieval and an unauthorized
chunk cannot enter the candidate set.

### Build the vector index

After Phase 4 ingestion, run:

```powershell
python scripts/index_chunks.py data/processed/book1.jsonl data/processed/book2.jsonl
```

The first execution downloads the configured open-source embedding model into
`data/models/`, then stores the vector database in `data/chroma/`. Both are
local, ignored by Git, and can be rebuilt from the source PDFs.

### Current indexing verification

The current collection contains 173 records: 158 access-filtered Book 1
records and 15 access-filtered Book 2 records. The automated tests verify that
user-specific Chroma queries return only the permitted book, while an admin
query can access both.

## Phase 6: BM25 sparse keyword retrieval

### Purpose

Add lexical retrieval so searches can match exact terms and names that semantic
vector search may rank poorly. BM25 complements Phase 5's dense search; this
phase does not yet combine the two retrieval methods into hybrid search.

### What was built

1. A configurable BM25 index generated from the Phase 4 JSONL chunks.
2. A local JSONL index at `data/bm25/index.jsonl` by default; generated index
   data is ignored by Git and can be rebuilt from the processed chunks.
3. One scalar `allowed_user_id` record per permitted user, matching the secure
   indexing strategy used for dense retrieval.
4. A BM25 search implementation that builds separate ranked corpora per user.
   A normal user searches only their own corpus; the admin index is deduplicated
   across authorized records.
5. Configurable result count with `TOP_K_BM25` (default: 10).
6. Tests for per-user isolation, admin access, index generation, and empty or
   invalid searches.

### Build the sparse index

After running the Phase 4 PDF ingestion commands, build the sparse index with:

```powershell
python scripts/index_bm25.py data/processed/book1.jsonl data/processed/book2.jsonl
```

The command writes `data/bm25/index.jsonl`. To choose another destination, use
`--output`, or set `BM25_INDEX_PATH` in `.env`. `rank-bm25` is installed with
the project's requirements.

BM25 search is exposed as a backend retrieval component in
`backend/app/rag/bm25.py`; chat/API integration is not part of this phase.
Access authorization is applied when constructing each user's corpus, before
query ranking, and results include their source and page metadata.

## Phase 7: Hybrid dense + sparse retrieval

### Purpose

Combine semantic similarity from Chroma with exact-term matching from BM25.
Dense distances and BM25 scores use different numeric scales, so the
implementation uses reciprocal rank fusion (RRF) instead of adding raw scores.

### What was built

1. A hybrid retrieval module in `backend/app/rag/hybrid.py`.
2. Authorized dense and sparse searches are run independently before their
   rankings are fused.
3. Results are deduplicated by the stable `chunk_id`, so a chunk returned by
   both retrievers appears once.
4. RRF rewards chunks present in both rankings and preserves each result's
   dense and sparse rank for later inspection or reranking.
5. A fail-closed authorization check at the fusion boundary prevents a normal
   user from receiving a result whose scalar `allowed_user_id` is different
   from the authenticated user. Admins can combine results from both books.
6. Configurable `TOP_K_HYBRID` (default: 10) and `HYBRID_RRF_K` (default: 60).
7. Tests for fusion ordering, deduplication, user isolation, admin access, and
   invalid limits.

### How to use hybrid retrieval

The high-level function accepts the existing Chroma collection, a query
embedding, the loaded BM25 index, the original text query, and the authenticated
user:

```python
from app.rag.bm25 import load_bm25_index
from app.rag.hybrid import search_hybrid

results = search_hybrid(
    collection,
    query_embedding,
    load_bm25_index(),
    query,
    current_user,
)
```

The function does not create or rebuild either index. Build the dense and
sparse indexes first using the Phase 5 and Phase 6 commands.

## Phase 8: Cross-encoder reranking

### Purpose

Improve the ordering of the small hybrid candidate set by scoring each
query-document pair with a cross-encoder. Unlike independent embeddings,
cross-encoders read the query and candidate text together, which usually gives
better final relevance ordering.

### What was built

1. A configurable local Sentence Transformers cross-encoder using
   `cross-encoder/ms-marco-MiniLM-L-6-v2` by default.
2. Lazy model loading so importing the retrieval module does not download a
   model; the model is loaded only when reranking is requested.
3. A fail-closed authorization check before candidate text is sent to the
   cross-encoder.
4. Deterministic ranking by cross-encoder score with `chunk_id` tie-breaking.
5. Validation for empty queries, invalid limits, and mismatched model outputs.
6. Configurable `RERANKER_MODEL` and `TOP_K_RERANKED` (default: 5).
7. Focused tests for ordering, user isolation, admin access, and validation.

### How to use reranking

```python
from app.rag.reranking import CrossEncoderReranker

reranker = CrossEncoderReranker()
reranked_results = reranker.rerank(
    query,
    hybrid_results,
    current_user,
)
```

The cross-encoder is applied only to the authorized hybrid candidates; it is
not an authorization mechanism. Build and query the Phase 5-7 indexes first,
then pass the hybrid results to the reranker. The first real reranking call
downloads the configured model into the local embedding cache.

## Phase 9: Grounded RAG answer generation

### Purpose

Turn the authorized reranked chunks into a grounded answer without allowing the
model to decide which documents the user may access. The backend selects and
formats the context first; the model receives only that context.

### What was built

1. A provider-neutral generation module in `backend/app/rag/generation.py`.
2. Authorization filtering before context is assembled and before candidate text
   is sent to the chat model.
3. A strict grounded prompt that tells the model to use only supplied context,
   admit when the context is insufficient, and cite evidence with markers such
   as `[1]`.
4. Stable source citations containing book name, source filename, and page
   number, for example `"[1] Book 1, book1.pdf, page 42"`.
5. A `GroundedAnswer` result containing the answer, citations, and context count.
6. Validation for empty queries, missing authorized context, empty model output,
   and unsupported model response shapes.
7. Configurable `MAX_CONTEXT_ITEMS` (default: 5) to cap prompt context.

### How to use grounded generation

```python
from app.rag.generation import GroundedAnswerGenerator

generator = GroundedAnswerGenerator(chat_model)
result = generator.generate(query, reranked_results, current_user)
print(result.answer)
print(result.citations)
```

`chat_model` is intentionally provider-neutral and only needs an `invoke`
method that accepts role/content messages. This keeps the retrieval and
authorization code independent from provider-specific integrations. Phase 15
adds a Groq streaming adapter for chat responses; an application can separately
adapt a configured model to the `invoke` interface required here. The FastAPI
chat endpoint currently streams conversation messages directly and does not
yet route them through the RAG supervisor.

## Phase 10: Safe calculator tool

### Purpose

Provide deterministic arithmetic without asking an LLM to calculate. The
calculator accepts basic numeric expressions and percentage-of expressions,
while rejecting arbitrary Python code and unsupported syntax.

### What was built

1. An explicit calculator tool in `backend/app/tools/calculator.py`.
2. AST-based evaluation of addition, subtraction, multiplication, division,
   powers, modulo, unary signs, parentheses, and expressions such as
   `15% of 2500`.
3. No `eval`, `exec`, imports, attribute access, function calls, names, or
   collection literals are permitted.
4. Input-length and result-range limits to prevent abusive calculations.
5. Structured `CalculationResult` output and explicit `CalculatorError`
   failures.
6. Tests for valid arithmetic, percentages, unsafe expressions, division by
   zero, oversized input, and unbounded results.

### How to use the calculator

```python
from app.tools.calculator import calculate

result = calculate("125 * 48")
print(result.value)  # 6000
```

The tool is intentionally independent from the LLM. It does not execute
arbitrary tool names or accept code.

### Next phases

Phase 11 adds configurable web search; Phase 12 adds the LangGraph supervisor.

## Phase 11: Configurable web search

### Purpose

Provide current external information through an explicit tool rather than
pretending that a language model's internal knowledge is current. Search
results are returned as untrusted external evidence with source URLs and are
not mixed into the private-book authorization model.

### What was built

1. A provider-neutral web-search tool in `backend/app/tools/web_search.py`.
2. Tavily support through its search API and optional Serper support through
   Google Serper's search API.
3. Provider selection through `WEB_SEARCH_PROVIDER=tavily` or `serper`.
4. Structured `WebSearchResponse` and `WebSearchResult` values containing
   title, URL, snippet, and provider source.
5. URL validation that keeps only `http://` and `https://` results.
6. Bounded result counts (1-20), configurable request timeout, and explicit
   provider/API-key/payload errors.
7. Tests for both provider payloads, invalid inputs, missing configuration,
   malformed responses, and network failures.

### Configure and use web search

Set the provider and only the key for the provider you use in `.env`:

```env
WEB_SEARCH_PROVIDER=tavily
TAVILY_API_KEY=your-tavily-key
WEB_SEARCH_MAX_RESULTS=5
WEB_SEARCH_TIMEOUT_SECONDS=10
```

Or use Serper:

```env
WEB_SEARCH_PROVIDER=serper
SERPER_API_KEY=your-serper-key
```

The keys are read only from environment settings and must never be committed.
Example usage:

```python
from app.tools.web_search import search_web

response = search_web("latest information about ...")
for result in response.results:
    print(result.title, result.url)
```

The tool uses a bounded HTTP request and returns external evidence; it does
not summarize or send web content to the LLM by itself.

### Next phases

Phase 12 adds the LangGraph supervisor for RAG, web, calculator, and direct
response routing. Later phases add multi-agent delegation, conversation
history, streaming, and the chat UI.

## Phase 12: LangGraph supervisor

### Purpose

Put an explicit orchestration boundary above the existing retrieval and tool
modules. The supervisor routes one authenticated request to exactly one
allowlisted worker: RAG, web search, calculator, direct response, or bounded
multi-agent delegation.

### What was built

1. A typed `AgentState` containing only the question, user identity, role,
   selected route, and response.
2. A compiled LangGraph in `backend/app/agents/supervisor.py` with conditional
   edges for `RAG`, `WEB`, `CALCULATOR`, `DIRECT`, and `DELEGATE`.
3. A deterministic default route decider that needs no model or network call.
4. Injected worker handlers so the existing RAG generation, web-search, and
   calculator functions can be wired in without coupling the graph to a
   provider.
5. Hard-coded question length, identity, route allowlist, and non-empty output
   checks. Invalid model/router decisions fail explicitly instead of falling
   through to an arbitrary tool.
6. Tests using fake handlers that verify every route, user identity
   propagation, invalid-route rejection, and worker failure behavior.

### How the graph works

```text
authenticated request
        |
        v
   supervisor
 /   |    |   |    \
RAG WEB CALC DIRECT DELEGATE
 \   |    |   |    /
    validated response
```

The graph does not grant authorization itself. The injected RAG handler must
continue to call the existing access-filtered retrieval and grounded
generation path, while the calculator and web handlers remain independently
validated tools. This keeps routing separate from business logic and ensures
that an LLM or route decider cannot bypass backend authorization.

The application-level worker bindings and authenticated chat route are
documented in [Runtime integration](#runtime-integration).

Example wiring:

```python
from app.agents.supervisor import SupervisorHandlers, run_supervisor

result = run_supervisor(
    SupervisorHandlers(
        rag=rag_handler,
        web=web_handler,
        calculator=calculator_handler,
        direct=direct_handler,
    ),
    question,
    user.id,
    user.role.value,
)
print(result["route"], result["response"])
```

### Next phases

Phase 13 implements bounded multi-agent delegation and synthesis.

## Phase 13: Multi-agent delegation

### Purpose

Support compound requests that require more than one capability, such as
looking up authorized book evidence, gathering current web information,
performing a calculation, and synthesizing the combined results.

### What was built

1. A typed `DelegationState` that carries the authenticated user identity,
   bounded plan, current step, specialist results, and final response.
2. A LangGraph workflow that executes specialist tasks sequentially in plan
   order and then invokes synthesis once.
3. A deterministic default planner for book/document, current-web, and
   calculation cues, plus an injectable planner for explicit subtask plans.
4. Hard limits of three distinct specialist steps, validated worker names and
   task text, and explicit failures for invalid plans or empty worker output.
5. Result retention that gives synthesis the original request and each
   specialist's structured target, task, and output.
6. Tests for the complete RAG -> web -> calculator -> synthesis sequence,
   custom task ordering, identity propagation, invalid plans, and worker or
   synthesis failures.

Example:

```python
from app.agents.delegation import DelegationHandlers, run_delegated_workflow

result = run_delegated_workflow(
    DelegationHandlers(
        rag=rag_handler,
        web=web_handler,
        calculator=calculator_handler,
        synthesize=synthesis_handler,
    ),
    question,
    user.id,
    user.role.value,
)
print(result["response"])
```

The default planner is deliberately bounded and heuristic; applications can
inject a model-backed planner, but its output is still validated against the
fixed worker allowlist and step limits. The workflow passes user identity and
role to every specialist. In particular, the RAG handler must continue using
the existing authorization-filtered retrieval path, and synthesis should treat
worker output (especially web content) as untrusted evidence.

The production runtime invokes this graph for compound requests that match
multiple specialist capabilities.

### Next phases

Phase 14 implements persistent, user-scoped conversation history. Streaming
is implemented in Phase 15; the complete chat UI is implemented in Phase 16.

## Phase 14: Conversation memory

### Purpose

Persist conversation records and messages while ensuring a user can only
list, retrieve, and append messages to conversations they own.

### What was built

1. SQLAlchemy `Conversation` and `ConversationMessage` models linked to their
   owning user, with creation/update timestamps and ordered message history.
2. Authenticated endpoints to create conversations, list the current user's
   conversations, retrieve one conversation with its messages, and append a
   user message.
3. Owner-scoped database queries for every operation. Missing and
   other-user-owned conversation IDs both return `404`.
4. Message content validation and a server-assigned `user` role on incoming
   messages, preventing clients from impersonating assistant output.
5. Tests for persistence, retrieval, authentication, input validation, and
   isolation between two users.

### Conversation API

| Endpoint | Method | What it does |
| --- | --- | --- |
| `/api/conversations` | POST | Creates an empty conversation for the authenticated user. |
| `/api/conversations` | GET | Lists only the authenticated user's conversations. |
| `/api/conversations/{conversation_id}` | GET | Retrieves one owned conversation and its messages. |
| `/api/conversations/{conversation_id}/messages` | POST | Persists a new user message in an owned conversation. |

All routes require a bearer access token. A conversation ID does not grant
access by itself; each query includes the authenticated user's immutable ID.
The service also supports persisting a validated assistant message after a
chat/agent request completes. The chat endpoint is documented in Phase 15.

### Next phases

Phase 15 implements model response streaming. Phase 16 adds the login,
history, and chat interface.

## Phase 15: Groq response streaming

### Configure Groq

Copy `.env.example` to `.env` if you have not already, then set these variables
in the root `.env` file. Never paste API keys into source files, README
examples, or `.env.example`.

```env
GROQ_API_KEY=your-new-groq-api-key
GROQ_MODEL=openai/gpt-oss-120b
GROQ_TIMEOUT_SECONDS=90
```

`GROQ_API_KEY` is the environment variable name read by the backend settings.
If you set it in a terminal instead, PowerShell can set it for that terminal
session with `$env:GROQ_API_KEY = "your-new-groq-api-key"`. Restart FastAPI
after changing `.env`.

### Troubleshoot Groq chat errors

The chat stream reports a safe, actionable message for common provider
failures: HTTP 401 means the key was rejected; 403 means the account or model
is not permitted; 404 usually means `GROQ_MODEL` is unavailable or misspelled;
and 429 indicates a rate limit or quota issue. Network and timeout failures
are reported separately. The backend terminal logs only the failure category
and HTTP status, never the API key or provider response body. After changing
`.env`, restart FastAPI so the new settings are loaded. A calculator-only
request does not require Groq.

### What was built

1. A provider adapter in `backend/app/llm/groq.py` using Groq's
   OpenAI-compatible streaming chat-completions API.
2. `POST /api/chat/stream`, protected by the existing bearer-token
   authentication and conversation ownership checks.
3. Server-sent `token`, `done`, and `error` events. The completed assistant
   response and the selected agent/source metadata are saved or returned;
   failed generations are not recorded as successful assistant messages.
4. A lightweight Streamlit streaming client. Phase 16 builds the complete
   login and conversation-history interface on top of this stream endpoint.
5. Tests with fake provider streams covering token delivery, persistence,
   invalid input, cross-user conversation denial, and provider errors.

### API request and stream format

Send a bearer access token and JSON request to `/api/chat/stream`:

```json
{
  "message": "Hello",
  "conversation_id": null
}
```

Omit `conversation_id` (or use `null`) to create a conversation. Subsequent
requests can send the `conversation_id` returned by the `done` event. Each
event is an SSE `data:` line containing JSON:

```json
{"type":"token","token":"Hello"}
{"type":"done","conversation_id":"...","message_id":"...","agent":"RAG Agent","sources":[{"title":"[1] Book, chapter.pdf, page 4","source":"chapter.pdf","page_number":"4"}]}
```

The provider key remains backend-only. If a key has been pasted into a
conversation, source file, or shared example, revoke it in the provider
dashboard and use a newly generated key in the ignored local `.env` file.

### Next phases

Phase 16 implements the Streamlit login, chat, conversation-history, sources,
agent-indicator, and logout experience.

## Phase 16: Streamlit frontend

### What was built

1. Login and account-registration forms using the existing FastAPI
   authentication routes. Access tokens are kept in Streamlit session state
   and shown only as masked input during authentication.
2. A user-scoped conversation history selector backed by the authenticated
   conversation API, plus a **New chat** action.
3. Streaming chat wired to `POST /api/chat/stream`, with the returned
   conversation ID retained for follow-up messages.
4. Assistant labels identify the actual selected agent. The UI renders
   citations from authorized RAG results and links from validated web results.
5. Logout clears authentication and conversation data from Streamlit session
   state.

The authenticated chat endpoint invokes the production worker bindings
documented below.

### Next phase

The Docker setup is documented in Phase 18 below.

## Phase 17: Security testing

### What was tested

1. JWT signature tampering and expired-token rejection.
2. Role-claim escalation attempts: authenticated user roles are loaded from
   the database, not trusted from editable token claims.
3. Document access fails closed for unauthorized or missing metadata, and
   unauthorized retrieved context is excluded before generation.
4. Conversation list/read/write isolation between different users.
5. Prompt-injection instructions in questions or retrieved context are
   explicitly treated as untrusted data in grounded-generation system prompts.
6. Calculator rejection of imports, file access, unsupported expressions, and
   abusive exponentiation.
7. A source/configuration scan that detects common Groq, Tavily, and OpenAI key
   formats in application source and committed documentation examples. It
   intentionally does not read the ignored local `.env` file.
8. Existing API tests also cover invalid tokens, unauthenticated requests,
   request bounds, and provider errors without leaking provider details.

Run the security-focused tests with:

```powershell
python -m pytest -q tests/test_auth.py tests/test_rbac.py tests/test_conversations.py tests/test_generation.py tests/test_security.py tests/test_calculator.py
```

These checks are regression safeguards, not a substitute for a professional
penetration test or provider-key rotation. If a real key has been pasted into
chat, logs, or a committed file, revoke it at the provider and issue a new one.

### Phase 18: Docker packaging

The root [Dockerfile](./Dockerfile) builds separate backend and frontend
targets. [docker-compose.yml](./docker-compose.yml) runs FastAPI and Streamlit,
waits for the backend health check before starting the UI, and keeps the
database, document indexes, processed files, and model cache in a named
Docker volume. Put PDFs in the ignored host folder `data/books/`; the backend
mounts that folder read-only. `.env` is passed only to the backend container;
it is excluded from Git and the Docker build context.

Create `.env` from `.env.example` and configure `JWT_SECRET_KEY` before
starting. Set `GROQ_API_KEY` for direct, grounded, and synthesized answers.
Set `TAVILY_API_KEY` or `SERPER_API_KEY` when using web search.

```powershell
docker compose up --build -d
docker compose ps
docker compose logs -f backend frontend
```

Open `http://localhost:8501` for the UI or `http://localhost:8000/docs` for the
API. Ingest books from the read-only mounted folder and build both indexes
inside the backend container:

```powershell
New-Item -ItemType Directory -Force data\books
docker compose exec backend python scripts/ingest_pdf.py /app/data/books/book1.pdf --book-id book1 --book-name "Book 1" --owner-username user1 --allowed-usernames user1
docker compose exec backend python scripts/index_chunks.py /app/data/processed/book1.jsonl
docker compose exec backend python scripts/index_bm25.py /app/data/processed/book1.jsonl
```

The generated account database and indexes persist in the Docker-managed
`app-data` volume. Stop containers while preserving that data with:

```powershell
docker compose down
```

To change host ports, set `BACKEND_PORT` or `FRONTEND_PORT` in the shell before
running Compose. The default ports are 8000 and 8501. `docker compose down -v`
removes the persistent application volume and its contents.

## Runtime integration

`POST /api/chat/stream` now runs through
`backend/app/agents/runtime.py`, which binds the authenticated request to the
LangGraph supervisor and its real application workers:

1. Direct conversation requests stream Groq output and include prior
   conversation messages.
2. Document requests run metadata-filtered Chroma and per-user BM25 retrieval,
   reciprocal-rank fusion, cross-encoder reranking, grounded Groq generation,
   and page/source citations.
3. Current-information requests call the configured Tavily or Serper provider,
   validate result URLs, synthesize only from untrusted search evidence, and
   return source links.
4. Arithmetic requests use the safe calculator without requiring a Groq key.
5. Requests indicating multiple specialist capabilities run the bounded
   sequential delegation graph, then stream only the final synthesis.
6. Assistant messages persist the selected agent and returned sources, so the
   conversation-history API and Streamlit source panel retain them after reload.

JWT authentication and conversation ownership remain enforced by FastAPI.
The chat endpoint passes an immutable user ID and server-resolved role into
workers; document authorization is enforced in retrieval before context is
sent to Groq. Web and document evidence is treated as untrusted input in the
answer and synthesis prompts.

For document questions, ingest documents and build both indexes before asking
the endpoint to search. RAG requests fail with a clear stream error if the
BM25 index is missing; an empty collection or no authorized matches produces
an explicit no-evidence answer rather than falling back to ungrounded chat.
Restart FastAPI after rebuilding indexes because the runtime caches loaded
retrieval components for the process lifetime.
On startup, FastAPI adds the agent/source columns to existing conversation
databases; older messages without stored metadata remain labeled as older
messages rather than being incorrectly presented as direct Groq replies.
Web search requires the selected provider's key in `.env`. Multi-agent
delegation is integrated for requests with multiple detected capabilities;
the routing and planning remain deterministic and bounded.

## Security principles

1. Passwords are hashed, never stored as plaintext.
2. JWT signing keys stay in `.env`, never source code.
3. The backend validates every bearer token.
4. The frontend is not treated as a security boundary.
5. Document authorization happens before retrieval results can reach an LLM.
6. Missing document-access metadata denies normal-user access.

## Agent implementation explanation

The project is intentionally structured around a small agent layer rather than a single prompt-to-model call. The design in `# AGENT.md` defines the rule that the backend is the security boundary and the agent is the routing boundary. In other words, the system should decide what capability is needed, then call the appropriate tool or retrieval path, and only then pass the resulting context to the LLM.

### Architectural flow

```text
User
  ↓
Streamlit frontend
  ↓
FastAPI backend
  ↓
JWT auth + RBAC
  ↓
LangGraph supervisor
  ├─ RAG → access-filtered Chroma + BM25 → hybrid ranking → reranker
  │       → grounded Groq answer + citations
  ├─ Web → Tavily/Serper → untrusted evidence → Groq answer + links
  ├─ Calculator → safe arithmetic tool
  ├─ Direct → Groq conversation (with prior messages)
  └─ Multiple capabilities → bounded delegation → synthesis
  ↓
SSE answer tokens + agent/source metadata
  ↓
Streamlit
```

This is not "User -> LLM -> answer". The LLM is the final reasoning component, not the gatekeeper for authorization or routing. The supervisor decides whether the request needs:

- a safe, user-scoped document lookup,
- an external web result,
- a calculator computation, or
- a direct conversational reply.

### Why the backend owns the decision path

The implementation follows this principle end to end. The backend validates
JWT tokens, loads the authenticated user, and enforces role checks before any
privileged action is allowed. The `get_current_user()` dependency ensures
every request is tied to a known user identity, and `require_role(...)` makes
admin-only actions explicit.

This matters because an agent is only as safe as the guardrails around it. If the frontend is treated as the security boundary, a user can bypass restrictions. The same is true if the model decides which documents it may read. The actual security control must happen before retrieval, not after.

### How the retrieval step is protected

The project stores document chunks with metadata including `book_id`, `book_name`, `owner_user_id`, `allowed_user_ids`, and `chunk_id`. During indexing, each record is replicated once per allowed user and the access metadata is flattened to a scalar field such as `allowed_user_id`.

This design ensures that a normal user's search query is filtered at the database/vector layer before the candidate set is built. In other words, a user asking for Book 2 never even sees Book 1 candidates, and a user who owns Book 1 never receives Book 2 chunks. The query looks like:

```python
where={"allowed_user_id": user.id}
```

for normal users, while admins query the full corpus. This is the exact pattern the AGENT.md calls for: authorization happens before retrieval and before the LLM receives any context.

### How the agent layer is integrated with the foundation

The current repository already gives the agent a stable base:

- FastAPI exposes endpoints and handles request lifecycle.
- SQLite stores user accounts and roles.
- JWT tokens carry identity and permissions.
- Chroma stores access-filtered retrieval candidates.
- Chunk metadata keeps document ownership and authorization information.

The production runtime binds the supervisor to the existing services and:

1. Receives the authenticated user and message from the FastAPI route.
2. Routes document, web, calculator, direct, or compound requests through
   allowlisted LangGraph nodes.
3. Executes authorized retrieval or the validated tool for the selected route.
4. Treats retrieved and external text as untrusted evidence during generation.
5. Returns streamed output, selected-agent metadata, and available sources.

### Summary

The real architecture is not a single chatbot. It is a controlled pipeline:

User request -> authenticated API -> routing supervisor -> authorized tool call -> filtered retrieval/context -> LLM -> response.

That is the design principle behind the implementation work in this repository: keep the security foundation explicit, keep agent routing modular, and make sure the model only works with context that has already been vetted by the backend.
