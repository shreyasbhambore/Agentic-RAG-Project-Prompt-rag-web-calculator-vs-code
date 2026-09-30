# Terminal Commands

Run these commands in **PowerShell from the project root**:

```powershell
Set-Location "C:\Users\sbe61\Downloads\Aiml-Engineer\New folder"
```

Replace example values such as `your-new-groq-api-key` and password
placeholders with your own values. Never put real credentials in this file,
source code, or `.env.example`.
For local startup, sample questions, and recovery steps for Python native
module import errors, see [TEST_COMMANDS.md](./TEST_COMMANDS.md).

## 1. Create and activate the Python environment

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
& ".\.venv\Scripts\python.exe" -m pip install --upgrade pip
& ".\.venv\Scripts\python.exe" -m pip install -r requirements.txt
```

If PowerShell blocks environment activation, activate the environment from a
Command Prompt instead:

```cmd
.venv\Scripts\activate.bat
```

## 2. Configure the application

Create the ignored local environment file if it does not exist:

```powershell
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
notepad .env
```

In `.env`, set the required values. Keep real secrets only in this ignored
local file:

```env
JWT_SECRET_KEY=replace-with-a-long-random-secret
GROQ_API_KEY=replace-with-a-new-groq-api-key
GROQ_MODEL=openai/gpt-oss-120b
TAVILY_API_KEY=
SERPER_API_KEY=
```

If you use web search, set the key for the selected `WEB_SEARCH_PROVIDER`
(`tavily` or `serper`). Restart the backend after changing `.env`.

## 3. Create the initial accounts

The seed script creates `admin`, `user1`, and `user2` only if they do not
already exist:

```powershell
python scripts/seed_users.py --admin-password "replace-with-a-strong-password" --user1-password "replace-with-a-strong-password" --user2-password "replace-with-a-strong-password"
```

Use strong, unique passwords. These command-line arguments can be visible in
terminal history and process listings; for a shared or production machine, use
a secure password-management procedure instead.

## 4. Add and index PDF books (optional)

Put PDFs under `data/books/`, then ingest each book. Adjust the source paths,
book names, owner usernames, and allowed usernames to match your documents and
users:

```powershell
python scripts/ingest_pdf.py data/books/book1.pdf --book-id book1 --book-name "Book 1" --owner-username user1 --allowed-usernames user1
python scripts/ingest_pdf.py data/books/book2.pdf --book-id book2 --book-name "Book 2" --owner-username user2 --allowed-usernames user2
```

Build the dense and sparse indexes from the processed chunks:

```powershell
python scripts/index_chunks.py data/processed/book1.jsonl data/processed/book2.jsonl
python scripts/index_bm25.py data/processed/book1.jsonl data/processed/book2.jsonl
```

Run only the index command(s) for the processed files you actually created.
The first dense-index run may download the embedding model.

## 5. Start the application

### Docker Compose (recommended)

With Docker Desktop running and `.env` configured:

```powershell
docker compose up --build -d
docker compose ps
docker compose logs -f backend frontend
```

Open `http://localhost:8501`. The API docs are available at
`http://localhost:8000/docs`. The database, processed PDFs, indexes, and
downloaded models persist in a Docker-managed volume. Put source PDFs under
`data/books/`; the backend container receives that folder read-only.

Run ingestion and index generation inside the container:

```powershell
docker compose exec backend python scripts/ingest_pdf.py /app/data/books/book1.pdf --book-id book1 --book-name "Book 1" --owner-username user1 --allowed-usernames user1
docker compose exec backend python scripts/index_chunks.py /app/data/processed/book1.jsonl
docker compose exec backend python scripts/index_bm25.py /app/data/processed/book1.jsonl
```

Use the commands from Section 4 with the appropriate book paths and user
permissions. Creating test users, when needed, can also be done with
`docker compose exec backend python scripts/seed_users.py` and the required
password arguments.

Stop the services without deleting local data:

```powershell
docker compose down
```

This preserves the app-data volume. `docker compose down -v` removes the
database, processed documents, indexes, and model cache stored there.

### Run directly with Python

Open two PowerShell terminals and run one command in each. These commands
call the `.venv` interpreter explicitly; activation is optional.

**Terminal 1 — backend:**

```powershell
& ".\.venv\Scripts\python.exe" -m uvicorn app.main:app --app-dir backend --reload
```

**Terminal 2 — Streamlit frontend:**

```powershell
& ".\.venv\Scripts\python.exe" -m streamlit run frontend/app.py
```

Open `http://localhost:8501` and sign in or create an account. To inspect or
call the API, open `http://localhost:8000/docs`.

## 6. Run tests

From the project root:

```powershell
& ".\.venv\Scripts\python.exe" -m pytest -q
```

## 7. Useful stop command

In the terminal running the backend or frontend, press:

```text
Ctrl+C
```
