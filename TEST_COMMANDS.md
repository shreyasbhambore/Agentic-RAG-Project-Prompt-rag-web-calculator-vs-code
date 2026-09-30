# Local Run and Streamlit Test Guide

This guide runs the application directly with Python on Windows PowerShell.
It does not use Docker.

## 1. Prepare the project (one time)

Open PowerShell in the project folder:

```powershell
Set-Location "C:\Users\sbe61\Downloads\Aiml-Engineer\New folder"
```

Create a virtual environment and install dependencies:

```powershell
python -m venv .venv
& ".\.venv\Scripts\python.exe" -m pip install --upgrade pip
& ".\.venv\Scripts\python.exe" -m pip install -r requirements.txt
& ".\.venv\Scripts\python.exe" -c "import pydantic_core; from pydantic_core import _pydantic_core; print('pydantic_core native extension OK')"
```

Use the `.venv\Scripts\python.exe` command shown here for application
commands as well; this avoids accidentally starting FastAPI or Streamlit with a
different Python interpreter selected on your machine. Activation is optional.

### If a native module cannot be imported

Errors such as a missing `pydantic_core._pydantic_core` or a NumPy binary
tagged for a different Python version mean `.venv` contains incompatible
compiled packages. Rebuild the whole environment instead of repairing one
package at a time. This renames the old environment as a backup, then installs
all dependencies into a new `.venv`:

```powershell
$OldVenv = ".venv-backup-$(Get-Date -Format 'yyyyMMdd-HHmmss')"
Move-Item -LiteralPath ".venv" -Destination $OldVenv
$BasePython = (Get-Command python).Source
& $BasePython --version
& $BasePython -m venv .venv
& ".\.venv\Scripts\python.exe" -m pip install --upgrade pip
& ".\.venv\Scripts\python.exe" -m pip install -r requirements.txt
& ".\.venv\Scripts\python.exe" -c "from pydantic_core import _pydantic_core; print('pydantic_core native extension OK')"
```

The base `python` must be the Python version you intend to use. The backed-up
environment is left in place until you decide it is safe to remove.

## 2. Configure local environment

Create `.env` from the example, then open it:

```powershell
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
notepad .env
```

Set `JWT_SECRET_KEY` to a long, private random value. For direct chat, RAG, or
web-answer synthesis, also set `GROQ_API_KEY` to a newly generated Groq API
key. Do not reuse any key previously pasted into a chat or committed file.
Never paste a real key into this guide or `.env.example`.

Web-search examples additionally need the key matching
`WEB_SEARCH_PROVIDER`:

```env
TAVILY_API_KEY=your-tavily-key
```

or:

```env
WEB_SEARCH_PROVIDER=serper
SERPER_API_KEY=your-serper-key
```

The calculator route does not call Groq or web search. It can be tried without
those provider keys once `JWT_SECRET_KEY` is set.

## 3. Users and administrator account

The **Create account** tab in Streamlit registers a normal `user` account.
Users cannot choose or promote their own role there. There is no admin user
management page in Streamlit.

For a local account with a chosen username and role, use the interactive
command. It prompts for a hidden password twice:

```powershell
& ".\.venv\Scripts\python.exe" scripts/manage_user.py --username alice --role user
& ".\.venv\Scripts\python.exe" scripts/manage_user.py --username admin --role admin
```

Use one command per account. Re-running the command for an existing account
replaces its password and role, so grant `admin` only to a trusted operator.
Log out and back in if the account was already signed in when it was updated.

To create the development admin and sample accounts, first ensure FastAPI has
started at least once (so the database tables exist), then run this from a
third PowerShell window in the project folder:

```powershell
& ".\.venv\Scripts\python.exe" scripts/seed_users.py --admin-password "use-a-unique-strong-password" --user1-password "use-another-strong-password" --user2-password "use-a-third-strong-password"
```

This creates `admin` with the `admin` role and `user1`/`user2` with the normal
`user` role. The script skips accounts that already exist; it does not upgrade
an existing normal account named `admin`. Passwords passed on the command line
may be visible in terminal history or process listings, so use this only for
local development and set unique passwords. The admin role can access the
managed document corpus; it is not a general-purpose admin dashboard.

To reset a password for an existing local account, use the interactive
utility. It prompts with hidden input and does not put the new password in
PowerShell history:

```powershell
& ".\.venv\Scripts\python.exe" scripts/reset_password.py alice
```

Enter and confirm a new 12-128 character password, then log out of Streamlit
and sign in again. Passwords cannot be retrieved; only password hashes are
stored.

## 4. Start FastAPI and Streamlit locally

Use two separate PowerShell terminals. In both terminals, go to the project
folder. The commands below call the virtual environment's Python explicitly,
so activation is not required.

**Terminal 1 — backend API:**

```powershell
Set-Location "C:\Users\sbe61\Downloads\Aiml-Engineer\New folder"
& ".\.venv\Scripts\python.exe" -m uvicorn app.main:app --app-dir backend --reload
```

Wait until Uvicorn reports that it is running. Check the API in a browser:

- Health endpoint: `http://localhost:8000/api/health`
- Interactive API docs: `http://localhost:8000/docs`

**Terminal 2 — Streamlit UI:**

```powershell
Set-Location "C:\Users\sbe61\Downloads\Aiml-Engineer\New folder"
& ".\.venv\Scripts\python.exe" -m streamlit run frontend/app.py
```

Open `http://localhost:8501`. Keep both terminals open while testing. The
Streamlit sidebar should show **Backend online**.

## 5. Create a test account and try the app

1. In Streamlit, choose **Create account**.
2. Enter a username (for example `alice`), a password of at least 12
   characters, and the same password in the confirmation field.
3. Choose **Create account**, then switch to **Log in** and sign in.
4. Type each example below into **Ask a question** and press Enter.
5. Check the agent label shown beneath each answer. Use **＋ New chat** to
   separate tests if you want a clean history.

| Try this question | Expected route / behavior |
|---|---|
| `Hi, can you help me?` | **Groq direct response**; requires `GROQ_API_KEY`. Follow-up questions use prior turns in that conversation. |
| `What is 15% of 240?` | **Calculator Agent**; expect `36.0`. Does not require Groq or web-search credentials. |
| `What is 18 * 7?` | **Calculator Agent**; expect `126`. |
| `Search the web for the latest space news.` | **Web Search Agent**; requires a configured Tavily or Serper key and a Groq key for the answer. Open **Sources** to see returned links. |
| `According to Book 1, what is Claude Code, and what three phases make up its agentic loop?` | **RAG Agent**; uses the bundled guide's "Getting Started" and "How Claude Code Works" sections; requires both indexes. |
| `According to Book 1, Claude Code repeats the phases gather context, take action, and verify results. Compare this workflow with the latest research on AI coding agents, and calculate 15% of 240.` | **Multi-agent synthesis**; expects the RAG and web prerequisites plus Groq. The plan is bounded to RAG, web and calculator tasks. |

If a route fails, check the backend terminal for the failure and confirm the
required credentials/indexes are ready. Provider errors are returned in a
user-safe form; provider secrets are not shown.

## 6. Optional: add a PDF for RAG tests

First create a Streamlit account and remember its exact username. Place a PDF
you are allowed to use in `data\books\`:

```powershell
New-Item -ItemType Directory -Force data\books
```

Use a third PowerShell terminal from the project root, activate `.venv`, then
replace `alice`, `sample.pdf`, and the book details below with your account,
PDF filename, and desired names:

```powershell
python scripts/ingest_pdf.py data/books/sample.pdf --book-id sample-book --book-name "Sample Book" --owner-username alice --allowed-usernames alice
python scripts/index_chunks.py data/processed/sample-book.jsonl
python scripts/index_bm25.py data/processed/sample-book.jsonl
```

The first dense-index run may download embedding and reranker models. Wait for
both index commands to finish, then restart the FastAPI terminal with
`Ctrl+C` and rerun the backend start command. Ask questions about material
that actually appears in that PDF. Only users listed in `--allowed-usernames`
can retrieve the book's chunks.

For the bundled Book 1, `alice` must be included in
`--allowed-usernames` if she should be able to ask about it. If chat reports
that document indexes are not ready, confirm that both the Chroma and BM25
index commands completed successfully, then restart FastAPI so it loads the
current indexes and code.

## 7. Try conversation history and access boundaries

1. Send two messages in a conversation, then select **＋ New chat**.
2. Reopen the first conversation from **Your conversations**. Confirm that the
   messages, agent labels, and available **Sources** are restored.
3. Create a second account in Streamlit and sign in as that user. Confirm that
   the first account's conversations are not listed.
4. If you indexed a book only for `alice`, ask about it while signed in as the
   second user. RAG should return no authorized passages rather than expose
   Alice's book.
5. Log out and sign back into Alice's account to check that her history is
   still present.

## 8. Stop the local application

In each terminal running Uvicorn or Streamlit, press:

```text
Ctrl+C
```

The SQLite database, processed documents, Chroma index, BM25 index, and model
cache are local under `data/`. Keep that folder to retain test data; do not
share it if it contains private documents or user information.
