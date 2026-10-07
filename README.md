# Proof — AI Hackathon Judge

An evidence-first local app for judging individual hackathon projects from their deployed URLs. A verified host signs in and uploads the participant details PDF with the numeric application ID. The app extracts the project name, one participant name, problem statement, and description, then runs a Playwright browser evaluation and creates an evidence-based report.

Team names and manually entered core feature lists are not collected. No slide deck or presentation is required.

## Start the app

Requirements: Docker Desktop and Docker Compose.

```powershell
docker compose up --build --detach
```

Open [http://localhost:3000](http://localhost:3000) for the public dashboard. Hosts and participants create accounts or sign in with Google. PostgreSQL stores accounts, submissions, and reports; Redis and a Celery worker run browser evaluations in the background.

## Set up Google sign-in

Create a Google OAuth client with application type **Web application**. Add `http://localhost:3000` as an authorized JavaScript origin and `http://localhost:8000/api/auth/google/callback` as an authorized redirect URI. Put its client ID and secret in the ignored local `.env` file:

```dotenv
GOOGLE_CLIENT_ID=your-client-id
GOOGLE_CLIENT_SECRET=your-client-secret
GOOGLE_REDIRECT_URI=http://localhost:8000/api/auth/google/callback
AUTH_SECRET_KEY=your-long-random-secret
```

Then run `docker compose up --build --detach`. Google verifies each account’s email on the server. Host sign-up creates a host account; participant sign-up also links the Google account to the participant’s numeric application ID. Participant sign-in uses that same Google account.

Stop the services with `docker compose down`. The database and uploaded PDFs remain in Docker volumes. `docker compose down -v` also deletes that local data.

## Host: add a project

Provide:

- The numeric application ID from the form response
- A text-based participant details PDF with one participant (up to 10 MB)
- The deployed project URL
- Optional public GitHub repository URL, for technical evidence

The PDF needs fields labeled **Project Name**, **Participant Name**, **Problem Statement**, and **Description** (or **Solution Description**). Scanned/image-only PDFs are not supported yet. The host can review the extracted details and uploaded PDF.

Participants use their application ID once during sign-up to link their Google account to the project. After that, they sign in with Google to view only their project details and evaluation. The source PDF and judging controls require a host account.

The deployed URL is the primary source for behavioral and usability evidence. GitHub manifests are used to verify technical indicators; README assertions are not counted as proof. Browser testing is read-only for potentially consequential actions: the judge does not submit valid forms, delete data, or make purchases.

## Published rubric

| Criterion | Weight |
|---|---:|
| Working Functionality | 30% |
| Problem Fit | 20% |
| Technical Complexity | 10% |
| UI/UX & Usability | 10% |
| Innovation & Originality | 20% |
| Real-World Problem Potential | 10% |
| **Total** | **100%** |

Each criterion displays its score, evidence references, points not awarded, and the specific evidence gap or weakness behind the missing points. The report separates browser observations from judge conclusions and flags low confidence or conflicting evidence for human review. Scores are not guaranteed to be perfect or final decisions.

## Google Gemini evaluations (optional)

The app does not include or automatically use an API key. Without a configured key, it falls back to deterministic scoring heuristics. To enable Google Gemini assessments, add your own key to the local, untracked `.env` file:

```dotenv
LLM_PROVIDER=google
LLM_BASE_URL=https://generativelanguage.googleapis.com/v1beta
LLM_API_KEY=your-google-ai-studio-key
LLM_MODEL=gemini-2.5-flash
```

Then restart the app with `docker compose up --build --detach api worker`. Keep the key in `.env`; do not commit it or paste it into source files. Gemini assessments are accepted only when their evidence references match observations recorded by the browser run. A model can still make mistakes, so human review remains available in the report.

## Tests

```powershell
cd backend
$env:PYTHONPATH = (Get-Location).Path
pytest
```

See `backend/app/judging/` for the browser, repository, scoring, and optional model evaluation modules. `backend/app/pdf_submission.py` extracts the participant PDF details.
