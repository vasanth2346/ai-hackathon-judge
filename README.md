# Proof — AI Hackathon Judge

An evidence-first app for judging hackathon projects from their deployed URLs. Hosts import participant rosters; participants create an account using an email on a host’s roster or sign in with Google, then submit project details. Submissions are routed to the host who imported that participant’s roster and evaluated with browser and repository evidence.

Team names and manually entered core feature lists are not collected. No slide deck or presentation is required.

## Start the app

Requirements: Docker Desktop and Docker Compose.

```powershell
docker compose up --build --detach
```

Open [http://localhost:3000](http://localhost:3000) for the public dashboard. Hosts use provisioned email/password accounts. Participants create accounts or sign in with Google. PostgreSQL stores accounts, submissions, and reports; Redis and a Celery worker run browser evaluations in the background. The Render Docker API service starts both the API and a judge worker by default. `JUDGE_WORKER_CONCURRENCY` defaults to 2; browser workers use significant memory, so raise concurrency or scale service instances only when the Render plan has enough memory.

Each host has a separate registration roster and project dashboard. Hosts can import a searchable PDF, CSV, or Excel `.xlsx`/`.xlsm` roster with participant names and email addresses (phone is optional). Participants can create an email/password account or use Google; the email must match a host-owned registration, and their submission is saved under that same host. A participant email must not be present in multiple host rosters because it would make the destination ambiguous.

## Set up Google sign-in

Create a Google OAuth client with application type **Web application**. Add `http://localhost:3000` as an authorized JavaScript origin and `http://localhost:8000/api/auth/google/callback` as an authorized redirect URI. Put its client ID and secret in the ignored local `.env` file:

```dotenv
GOOGLE_CLIENT_ID=your-client-id
GOOGLE_CLIENT_SECRET=your-client-secret
GOOGLE_REDIRECT_URI=http://localhost:8000/api/auth/google/callback
AUTH_SECRET_KEY=your-long-random-secret
```

Then run `docker compose up --build --detach`. Google verifies participant email on the server. Email/password participant account creation also requires an email present in a host’s uploaded roster. Hosts do not use Google sign-in or self-sign-up.

Configure host credentials in the ignored local `.env` file and in the backend deployment environment. Use `HOST_LOGIN_1_EMAIL`, `HOST_LOGIN_1_PASSWORD`, `HOST_LOGIN_2_EMAIL`, and `HOST_LOGIN_2_PASSWORD`. These values are secrets and must not be committed to the repository. Only the configured host emails can sign in.

## Deploy the website on Vercel

Vercel hosts the Next.js website only. The FastAPI service, Celery worker, PostgreSQL, and Redis must also be running on a backend host. In Vercel, set **Root Directory** to `frontend`. The deployed project uses `API_PROXY_TARGET` when present; otherwise its Vercel build proxies requests to the project’s Render API. If you use a different backend, add this variable for Production:

```dotenv
API_PROXY_TARGET=https://YOUR-BACKEND-DOMAIN
```

Do not set `NEXT_PUBLIC_API_URL` when using this proxy. The website routes `/api/...` requests through the backend using the same website domain, which lets Google sign-in session cookies work reliably. Redeploy the Vercel project after changing environment variables.

For a Render Docker web service, set its root directory to `backend/`, leave **Start Command** empty so Render uses the Dockerfile entrypoint, and configure these values in **Render → your API web service → Environment** (never put secrets in Vercel). The entrypoint starts the API and Celery worker together and restarts the worker if it exits. Set `JUDGE_WORKER_CONCURRENCY` according to the service memory. If you run a separate Render Background Worker instead, set `START_JUDGE_WORKER=false` on the API service and use `celery -A app.tasks.celery_app worker --loglevel=INFO --concurrency=2` as the worker Start Command; the API and worker must share the same database and Redis URLs.

```dotenv
FRONTEND_ORIGIN=https://YOUR-VERCEL-DOMAIN
DATABASE_URL=postgresql+psycopg://... (use Render's internal PostgreSQL URL and replace the scheme prefix)
REDIS_URL=redis://... (use the Redis-compatible service's internal URL)
GOOGLE_CLIENT_ID=your-web-oauth-client-id
GOOGLE_CLIENT_SECRET=your-web-oauth-client-secret
GOOGLE_REDIRECT_URI=https://YOUR-VERCEL-DOMAIN/api/auth/google/callback
AUTH_SECRET_KEY=your-long-random-secret
AUTH_COOKIE_SECURE=true
AUTH_COOKIE_SAMESITE=lax
HOST_LOGIN_1_EMAIL=host-account-one@example.edu
HOST_LOGIN_1_PASSWORD=use-a-private-password
HOST_LOGIN_2_EMAIL=host-account-two@example.edu
HOST_LOGIN_2_PASSWORD=use-a-private-password
```

Replace `YOUR-VERCEL-DOMAIN` with the exact production domain, without a trailing slash. In Google Cloud Console, add `https://YOUR-VERCEL-DOMAIN` as an **Authorized JavaScript origin** and `https://YOUR-VERCEL-DOMAIN/api/auth/google/callback` as an **Authorized redirect URI**. The Vercel `/api` rewrite forwards that callback to the Render API. Do not use the Render domain as the OAuth redirect URI when using this proxy. The API and worker must use the same database, Redis, encryption, Gemini, and OAuth environment settings. The frontend and API must both use HTTPS in production.

After deploying, open `https://YOUR-VERCEL-DOMAIN/api/health`; `database: "ok"` and `judge_worker_ready: true` confirm the API, database, and judge worker are connected. If worker readiness is false, check the Render service logs and ensure its Start Command is empty so the Dockerfile starts the worker. Open `https://YOUR-VERCEL-DOMAIN/api/auth/google/status` to check OAuth configuration without revealing secret values. The host dashboard also shows whether an AI provider and API key are configured. If you update backend environment values, redeploy the Render API. If you update Vercel environment values, redeploy the Vercel project.

Stop the services with `docker compose down`. The database and uploaded PDFs remain in Docker volumes. `docker compose down -v` also deletes that local data.

## Host: import a participant roster

Upload a searchable PDF, CSV, or Excel `.xlsx`/`.xlsm` roster containing participant name and email columns. Phone is optional. Each participant email must identify a single host roster so submissions go to the correct host. Scanned/image-only PDFs are not supported.

Participants can create an email/password account with the roster email or sign in with the matching Google account. They verify their profile and select a domain, then enter the project name, live URL, GitHub repository, problem statement, and description. A submission appears only in its roster owner’s host dashboard. Participant dashboards show submission status and project details, not evaluation scores or judge feedback. Every submission is queued immediately; available worker slots start evaluations in parallel. Celery returns interrupted jobs to the queue, and transient evaluation errors are retried. Hosts can manually retry an unfinished run after 15 minutes. Problem Fit compares the stated need with capabilities observed in the live app; verified repository code can support that assessment but does not prove it is deployed.

The deployed URL is the primary source for behavioral and usability evidence. GitHub manifests are used to verify technical indicators; README assertions are not counted as proof. Browser testing is read-only for potentially consequential actions: the judge does not submit valid forms, delete data, or make purchases.

## Published rubric

| Criterion | Weight |
|---|---:|
| Working Functionality | 25% |
| Problem Fit | 20% |
| Technical Complexity | 10% |
| UI/UX & Usability | 10% |
| Innovation & Originality | 25% |
| Real-World Problem Potential | 10% |
| **Total** | **100%** |

Each criterion displays its score, evidence references, points not awarded, and the specific evidence gap or weakness behind the missing points. The report separates browser observations from judge conclusions and flags low confidence or conflicting evidence for human review. Scores are not guaranteed to be perfect or final decisions.

## Google Gemini evaluations (optional)

The app does not include or automatically use an API key. Without a configured key, it falls back to deterministic scoring heuristics. To enable Google Gemini assessments, add your own key to the local, untracked `.env` file:

```dotenv
LLM_PROVIDER=google
LLM_BASE_URL=https://generativelanguage.googleapis.com/v1beta
LLM_API_KEY=your-google-ai-studio-key
LLM_MODEL=gemini-3.8-flash
```

Then restart the app with `docker compose up --build --detach api worker`. Keep the key in `.env`; do not commit it or paste it into source files. Gemini assessments are accepted only when their evidence references match observations recorded by the browser run. A model can still make mistakes, so human review remains available in the report.

## Tests

```powershell
cd backend
$env:PYTHONPATH = (Get-Location).Path
pytest
```

See `backend/app/judging/` for the browser, repository, scoring, and optional model evaluation modules. `backend/app/pdf_submission.py` extracts the participant PDF details.
