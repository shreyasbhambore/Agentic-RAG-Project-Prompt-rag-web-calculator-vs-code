AGENTIC RAG + WEB SEARCH - SIMPLE LOCAL TEST SCENARIO
=====================================================

Before starting
---------------
1. Use the project folder:
   C:\Users\sbe61\Downloads\Aiml-Engineer\New folder
2. Make sure the local .env has GROQ_API_KEY and GROQ_MODEL configured.
   Never put a real API key in this file.
3. Book 1 has been indexed and made available to the account named "alice".
   The backend should be restarted after rebuilding indexes.
4. Web-search tests require a valid key for the provider selected by
   WEB_SEARCH_PROVIDER in .env.

Start the application
---------------------
Open two PowerShell windows in the project folder.

Window 1 - FastAPI backend:

  Set-Location "C:\Users\sbe61\Downloads\Aiml-Engineer\New folder"
  & ".\.venv\Scripts\python.exe" -m uvicorn app.main:app --app-dir backend --reload

Window 2 - Streamlit frontend:

  Set-Location "C:\Users\sbe61\Downloads\Aiml-Engineer\New folder"
  & ".\.venv\Scripts\python.exe" -m streamlit run frontend/app.py

Open http://localhost:8501. Wait for the sidebar to show "Backend online".
Keep both PowerShell windows open while testing.

Log in
------
Choose the "Log in" tab.

  Username: alice
  Password: enter the password you chose when you registered alice.

Do not put your password in this file, screenshots, or messages. The password
previously shared in chat should be treated as exposed. The app currently has
no password-change screen, but you can securely reset a local account password
from PowerShell. From the project folder run:

  & ".\.venv\Scripts\python.exe" scripts\reset_password.py alice

Enter a new password of 12-128 characters twice when prompted. Input is hidden
and is not saved in shell history. The command changes the password stored for
the existing account; it does not reveal the old password. Log out from
Streamlit and log back in with the new one. Do not reuse the password shared
in chat for any account or service.

Questions to try, one at a time
-------------------------------

1. Direct chat
   Ask:
     Hi, can you help me?
   Expected:
     A normal answer and the label "Groq direct response".

2. Calculator
   Ask:
     What is 15% of 240?
   Expected:
     "15% of 240 = 36.0" and the label "Calculator Agent".

3. Ask about the book
   Ask:
     According to Book 1, what is Claude Code, and what three phases make up
     its agentic loop?
   Expected:
     A grounded answer and the label "RAG Agent". Open "Sources" to see the
     book/page citation. This question is based on the "Getting Started" and
     "How Claude Code Works" sections in Book 1.

4. Search current information
   Ask:
     Search the web for the latest research on how AI coding agents help
     software developers.
   Expected:
     A current-information answer, the label "Web Search Agent", and web
     links under "Sources". This requires a working configured web-search key.

5. Combine book, web, and calculation
   Ask:
     According to Book 1, Claude Code repeats the phases gather context, take
     action, and verify results. Compare this workflow with the latest
     research on AI coding agents, and calculate 15% of 240.
   Expected:
     The label "Multi-agent synthesis", a comparison based on Book 1 and web
     results, citations where available, and the calculation result 36.0.
     The web-search key must work for the latest-research part.

If something fails
------------------
- RAG says indexes are not ready: verify both indexes were built and restart
  FastAPI. Book 1 is currently authorized for "alice" and "user1".
- RAG returns no relevant evidence: ask about a topic actually present in
  Book 1.
- Web search fails: check WEB_SEARCH_PROVIDER and that provider's key in .env.
- Groq fails: check GROQ_API_KEY and GROQ_MODEL in .env, then restart FastAPI.
- A plain greeting does not normally have document or web citations.

Stop the application
--------------------
Press Ctrl+C in each PowerShell window running FastAPI or Streamlit.
