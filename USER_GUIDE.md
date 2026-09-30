# Run the app after downloading the GitHub ZIP

This guide is for a fresh Windows download. It assumes you have not used this
app on this computer before. Commands below are for PowerShell.

## 1. Extract the ZIP and open the project folder

1. On GitHub, select **Code > Download ZIP**.
2. Extract the ZIP (do not run the app from inside the compressed ZIP).
3. Open the extracted project folder in File Explorer.
4. Open PowerShell in that folder: click the address bar, type `powershell`,
   and press Enter.
5. Check that you are in the project root:

   ```powershell
   Get-ChildItem requirements.txt, .env.example, backend, frontend, scripts
   ```

   The command should list those files and folders. If it says they cannot be
   found, change directory to the extracted folder first.

## 2. Install Python dependencies

Install Python 3.13 for Windows if it is not already installed. In PowerShell,
check it with:

```powershell
py -3.13 --version
```

From the project root, create a virtual environment and install the packages:

```powershell
py -3.13 -m venv .venv
& ".\.venv\Scripts\python.exe" -m pip install --upgrade pip
& ".\.venv\Scripts\python.exe" -m pip install -r requirements.txt
& ".\.venv\Scripts\python.exe" -m pip check
```

Wait for installation to finish. The first setup may take several minutes.
Always use `.venv\Scripts\python.exe` for the app commands below.

## 3. Add your local settings

Create your private `.env` file and open it:

```powershell
Copy-Item .env.example .env
notepad .env
```

Set these values in Notepad:

```env
JWT_SECRET_KEY=replace-this-with-a-long-random-private-value
GROQ_API_KEY=paste-your-own-Groq-key-here
GROQ_MODEL=openai/gpt-oss-120b
```

For web-search questions, also configure a key for the selected provider. For
example, with the default Tavily provider:

```env
WEB_SEARCH_PROVIDER=tavily
TAVILY_API_KEY=paste-your-own-Tavily-key-here
```

Or, for Serper:

```env
WEB_SEARCH_PROVIDER=serper
SERPER_API_KEY=paste-your-own-Serper-key-here
```

Replace the example values; do not include angle brackets, and do not add
quotes around the values. Keep `.env` private: never upload it, commit it, or
paste keys into a chat. Save Notepad and close it. A calculator question only
needs the app's `JWT_SECRET_KEY`; direct chat also needs a valid Groq key.

## 4. Start the backend and frontend

Open **two PowerShell windows** in the extracted project root.

In the first window, start FastAPI:

```powershell
& ".\.venv\Scripts\python.exe" -m uvicorn app.main:app --app-dir backend --reload
```

Leave it running. Wait until Uvicorn says it is running. You can check the API
at <http://localhost:8000/api/health>.

In the second window, start Streamlit:

```powershell
& ".\.venv\Scripts\python.exe" -m streamlit run frontend/app.py
```

Open <http://localhost:8501>. The sidebar should say **Backend online**.
Leave both windows running while using the app.

## 5. Create an account and log in

1. In Streamlit, select **Create account**.
2. Choose a username, for example `alice`.
3. Choose a new, unique password of at least 12 characters; enter it twice.
   Do not reuse a password that has been shared or used on another site.
4. Create the account, select **Log in**, and sign in with the username and
   password you just chose.

The app does not set a standard password for Alice. You create the password
when you register. If you forget it, close the prompt and use the local reset
command in the next section.

### Create or change a user/admin account from PowerShell

Streamlit's **Create account** tab always creates a normal `user` account.
If you want to choose the username and role from a local command, run
`manage_user.py` from the project root. It prompts for the password twice
without displaying it or placing it in command history.

Create a regular user:

```powershell
& ".\.venv\Scripts\python.exe" scripts\manage_user.py --username alice --role user
```

Create an administrator:

```powershell
& ".\.venv\Scripts\python.exe" scripts\manage_user.py --username admin --role admin
```

The username must be 3-64 characters using letters, numbers, `_` or `-`; the
password must be 12-128 characters. Run the command again for an existing
username to replace its password and role. Do not run it on an existing
account unless you intend to reset its password and set the selected role.
Grant `admin` only to a trusted operator: admins can retrieve the managed
document corpus. This local command does not add an admin dashboard to
Streamlit. If you update an account that is currently signed in, log out and
sign in again to use the changed role.

## 6. Try these questions

Enter one question at a time in **Ask a question**:

| Question | Expected result |
|---|---|
| `Hi, can you help me?` | A Groq reply labeled **Groq direct response**. |
| `What is 15% of 240?` | **Calculator Agent** returns `36.0`. |
| `Search the web for the latest research on how AI coding agents help software developers.` | **Web Search Agent** returns an answer with links under **Sources**. Requires a working web-search key and Groq. |

For document search, first follow **Add your own PDF for RAG** below. The
GitHub ZIP does not include your local `.env`, database, indexes, or other
files ignored by Git. Do not assume your locally indexed books transfer in a
fresh download.

## 7. Add your own PDF for RAG (optional)

Register and log in to Streamlit first. Use a PDF you are allowed to process.
In a third PowerShell window at the project root, replace the path, book
details, and `alice` with your own file and exact registered username:

```powershell
New-Item -ItemType Directory -Force data\books
Copy-Item "C:\path\to\your\book.pdf" "data\books\my-book.pdf"
& ".\.venv\Scripts\python.exe" scripts\ingest_pdf.py data\books\my-book.pdf --book-id my-book --book-name "My Book" --owner-username alice --allowed-usernames alice
& ".\.venv\Scripts\python.exe" scripts\index_chunks.py data\processed\my-book.jsonl
& ".\.venv\Scripts\python.exe" scripts\index_bm25.py data\processed\my-book.jsonl
```

The first dense-index build may download embedding/reranker models. Wait for
both index commands to finish. Restart FastAPI (press Ctrl+C in its window and
run the backend command again). Then ask a question whose answer is actually
in your PDF, for example:

```text
According to My Book, what are the main recommendations in the introduction?
```

If that subject is not in your PDF, change the question to something that is.
Only usernames listed in `--allowed-usernames` can search the PDF. Use the
same username and book access when re-running ingestion if you change who may
read it.

## 8. Test RAG, web search, and calculator together (optional)

After adding a PDF and configuring web search, ask:

```text
According to My Book, summarize the recommendations in its introduction, compare them with the latest research on those recommendations, and calculate 15% of 240.
```

Expected: **Multi-agent synthesis**, relevant book and web sources, and the
calculation `36.0`. This requires an indexed PDF, a working web-search key, and
a working Groq key. If your document is about another subject, replace
“recommendations in its introduction” with a question about that document.

## 9. Reset a forgotten local password

From a PowerShell window at the project root, run:

```powershell
& ".\.venv\Scripts\python.exe" scripts\reset_password.py alice
```

Enter and confirm a new password (12-128 characters) at the hidden prompts.
It is not displayed or saved in PowerShell history. Log out of Streamlit and
log back in with the new password. Use your account name instead of `alice` if
you chose another username.

## 10. Stop the app

Press **Ctrl+C** in both the FastAPI and Streamlit PowerShell windows.

## Common problems

- **Backend unavailable:** make sure FastAPI is still running in the first
  window and the Streamlit page says **Backend online**.
- **Groq returns HTTP 401:** check that `GROQ_API_KEY` is your valid key.
- **Groq returns HTTP 404:** check `GROQ_MODEL=openai/gpt-oss-120b`, then
  restart FastAPI.
- **RAG says indexes are not ready:** run both index commands and restart
  FastAPI.
- **RAG finds no passages:** check that the PDF contains selectable text, that
  the question matches its contents, and that your username is in
  `--allowed-usernames`.
- **Web search fails:** confirm the selected `WEB_SEARCH_PROVIDER` has a valid
  corresponding API key in `.env`.
- **The first PDF/model run is slow:** model downloads are expected; wait for
  the commands to finish before asking questions.
