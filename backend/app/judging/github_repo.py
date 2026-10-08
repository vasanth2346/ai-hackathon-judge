import base64
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote, urlparse

import httpx

from app.config import get_settings

MANIFESTS = ["package.json", "pyproject.toml", "requirements.txt", "Pipfile", "Cargo.toml", "go.mod", "pom.xml", "build.gradle", "build.gradle.kts", "composer.json", "Gemfile", "Dockerfile"]


async def inspect_repository(url: str | None, run_id: str):
    if not url:
        return [], [], None
    parsed = urlparse(url)
    parts = [part for part in parsed.path.strip("/").split("/") if part]
    observations, evidence = [], []
    if parsed.hostname != "github.com" or len(parts) < 2 or not all(re.fullmatch(r"[A-Za-z0-9_.-]+", p) for p in parts[:2]):
        observations.append({"id": "obs-repo-001", "kind": "repository", "title": "Repository URL not supported", "detail": "Only a public github.com owner/repository URL can be inspected in this MVP.", "result": "not_tested", "observed_at": datetime.now(timezone.utc).isoformat()})
        return observations, evidence, None
    owner, repo = parts[0], parts[1].removesuffix(".git")
    base = f"https://api.github.com/repos/{owner}/{repo}"
    headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "HackathonJudge/0.1"}
    verified_files, source_files, metadata = {}, {}, None
    async with httpx.AsyncClient(timeout=12, follow_redirects=False, headers=headers) as client:
        try:
            response = await client.get(base)
            observations.append({"id": "obs-repo-001", "kind": "repository", "title": "Public GitHub repository checked", "detail": f"GitHub API returned HTTP {response.status_code} for {owner}/{repo}.", "result": "passed" if response.status_code == 200 else "failed", "observed_at": datetime.now(timezone.utc).isoformat()})
            if response.status_code != 200:
                return observations, evidence, None
            metadata = response.json()
            if metadata.get("private"):
                observations[-1]["detail"] += " Repository is private; no files were read."
                return observations, evidence, None
            branch = metadata.get("default_branch", "")
            for filename in MANIFESTS:
                file_response = await client.get(f"{base}/contents/{filename}", params={"ref": branch})
                if file_response.status_code != 200:
                    continue
                payload = file_response.json()
                if payload.get("encoding") != "base64" or not isinstance(payload.get("content"), str):
                    continue
                try:
                    content = base64.b64decode(payload["content"]).decode("utf-8", errors="replace")[:60000]
                except (ValueError, TypeError):
                    continue
                verified_files[filename] = content
            tree_response = await client.get(f"{base}/git/trees/{quote(branch, safe='')}?recursive=1")
            if tree_response.status_code == 200:
                tree = tree_response.json().get("tree", [])
                paths = [entry.get("path", "") for entry in tree if entry.get("type") == "blob" and re.search(r"\.(?:py|ts|tsx|js|jsx|go|rs|java|cs|php|rb)$", entry.get("path", ""), re.I)]
                paths = [path for path in paths if not any(part.lower() in {"node_modules", "vendor", "dist", "build", ".next", "coverage"} for part in path.split("/"))]
                for path in paths[:8]:
                    source_response = await client.get(f"{base}/contents/{quote(path, safe='/')}", params={"ref": branch})
                    if source_response.status_code != 200:
                        continue
                    source_payload = source_response.json()
                    if source_payload.get("encoding") != "base64" or not isinstance(source_payload.get("content"), str):
                        continue
                    try:
                        source_files[path] = base64.b64decode(source_payload["content"]).decode("utf-8", errors="replace")[:20000]
                    except (ValueError, TypeError):
                        continue
        except (httpx.HTTPError, ValueError) as exc:
            observations.append({"id": "obs-repo-001", "kind": "repository", "title": "Repository inspection failed", "detail": str(exc)[:800], "result": "failed", "observed_at": datetime.now(timezone.utc).isoformat()})
            return observations, evidence, None

    languages = {}
    try:
        async with httpx.AsyncClient(timeout=10, headers=headers) as client:
            language_response = await client.get(f"{base}/languages")
            if language_response.status_code == 200:
                languages = language_response.json()
    except httpx.HTTPError:
        pass
    indicators = []
    combined = "\n".join(verified_files.values()).lower()
    checks = {"Next.js": '"next"' in combined, "React": '"react"' in combined, "FastAPI": "fastapi" in combined, "Playwright": "playwright" in combined, "PostgreSQL driver": any(x in combined for x in ("psycopg", "asyncpg", "pg")), "Redis client": "redis" in combined, "Celery": "celery" in combined, "Tailwind CSS": "tailwindcss" in combined, "scikit-learn": "scikit-learn" in combined, "PyTorch": "torch" in combined, "TensorFlow": "tensorflow" in combined, "OpenAI client": "openai" in combined}
    indicators.extend(name for name, present in checks.items() if present)
    source_paths = list(source_files)
    source_combined = "\n".join(source_files.values()).lower()
    # Give the evaluator a small, bounded sample of verified implementation
    # relevant to problem fit. The live browser observations remain primary.
    problem_fit_excerpt = "\n\n".join(
        f"--- {path} ---\n{content[:1800]}"
        for path, content in list(source_files.items())[:5]
    )[:7000]
    code_signals = {
        "frontend_source": any(re.search(r"(?:^|/)src/(?:app|pages)/|(?:^|/)(?:pages|app)/.*\.(?:tsx?|jsx?)$", path, re.I) for path in source_paths),
        "backend_source": any(re.search(r"(?:^|/)(?:main|server|app|routes?|api)\.(?:py|js|ts|go|rs)$", path, re.I) for path in source_paths),
        "tests_present": any(re.search(r"(?:^|/)(?:tests?|__tests__)(?:/|$)|\.(?:test|spec)\.", path, re.I) for path in source_paths),
        "database_logic": bool(re.search(r"\b(?:sqlalchemy|prisma|drizzle|mongoose|psycopg|asyncpg|sqlite|postgres|mysql|create_table|select\s+.+\s+from)\b", source_combined)),
        "api_integration": bool(re.search(r"\b(?:fetch\s*\(|axios|httpx|requests\.|urllib|api[_-]?route|router\.(?:get|post)|@app\.(?:get|post))", source_combined)),
    }
    saved = get_settings().evidence_dir / run_id / "github-source-snapshot.txt"
    saved.parent.mkdir(parents=True, exist_ok=True)
    saved.write_text("\n\n".join([*(f"--- {name} ---\n{body}" for name, body in verified_files.items()), *(f"--- SOURCE {name} ---\n{body}" for name, body in source_files.items())]), encoding="utf-8")
    evidence.append({"id": "evi-repo-001", "kind": "repository_snapshot", "title": "Fetched dependency manifests and selected source files", "file": saved.name, "path": str(saved), "source_url": url, "files": list(verified_files) + source_paths, "captured_at": datetime.now(timezone.utc).isoformat()})
    observations.append({"id": "obs-repo-002", "kind": "technology_verification", "title": "Technology and source structure checked", "detail": f"Read {', '.join(verified_files) or 'no supported dependency manifests'} and {len(source_paths)} selected source file(s) from the public default branch. Verified indicators: {', '.join(indicators) or 'none detected'}. Source signals: {', '.join(name for name, present in code_signals.items() if present) or 'none detected'}. README claims were not used to verify these technologies.", "result": "observed", "verified_files": list(verified_files), "source_files": source_paths, "indicators": indicators, "code_signals": code_signals, "language_bytes": languages, "evidence_id": "evi-repo-001", "observed_at": datetime.now(timezone.utc).isoformat()})
    return observations, evidence, {"indicators": indicators, "languages": languages, "files": list(verified_files), "source_files": source_paths, "code_signals": code_signals, "problem_fit_code_excerpt": problem_fit_excerpt, "stars": metadata.get("stargazers_count"), "license": (metadata.get("license") or {}).get("spdx_id")}
