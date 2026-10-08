import asyncio
import ipaddress
import re
import socket
from datetime import datetime, timezone
from urllib.parse import urlparse
from uuid import uuid4

from playwright.async_api import async_playwright

from app.config import get_settings


def stamp():
    return datetime.now(timezone.utc).isoformat()


def public_http_url(url: str) -> bool:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
        return False
    try:
        addresses = {item[4][0] for item in socket.getaddrinfo(parsed.hostname, parsed.port or (443 if parsed.scheme == "https" else 80))}
        return bool(addresses) and all(ipaddress.ip_address(addr.split("%", 1)[0]).is_global for addr in addresses)
    except (OSError, ValueError):
        return False


def classify_product_surface(url: str, title: str, visible_text: str) -> tuple[bool | None, str]:
    """Separate a participant product from hosting/control-panel pages."""
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    title_lower = title.lower()
    text_lower = re.sub(r"\s+", " ", visible_text).strip().lower()
    if (host in {"vercel.com", "app.vercel.com"} and (parsed.path.lower().startswith(("/login", "/signup", "/sso-api")) or "sign in" in title_lower)):
        return None, "The deployment redirected to Vercel authentication; the participant application itself was not publicly visible."
    if host in {"vercel.com", "app.vercel.com"} and (
        "overview" in title_lower or "project settings" in title_lower or len(parsed.path.strip("/").split("/")) >= 2
    ):
        return False, "This is a Vercel account or project console, not the deployed participant application."
    control_hosts = {
        "app.netlify.com", "console.cloud.google.com", "console.firebase.google.com",
        "dashboard.heroku.com", "console.aws.amazon.com", "cloud.mongodb.com",
        "fly.io", "dashboard.render.com",
    }
    if host in control_hosts:
        return False, "This URL opens a hosting or cloud control panel, not the deployed participant application."
    login_only = bool(re.search(r"\b(sign in|log in|login|authenticate|continue with google|continue with github)\b", title_lower + " " + text_lower)) and bool(re.search(r"\b(email|password|account|identity provider|authentication)\b", text_lower))
    if login_only:
        return None, "Only a sign-in screen was visible; the participant application could not be verified."
    if len(text_lower) < 30:
        return None, "The page exposed too little readable content to confirm that it is the participant application."
    return True, "A readable public application page was observed."


def record(observations: list, kind: str, title: str, detail: str, **extra):
    item = {"id": f"obs-{len(observations) + 1:03d}", "kind": kind, "title": title, "detail": detail[:1800], "observed_at": stamp()}
    item.update(extra)
    observations.append(item)
    return item["id"]


async def inspect_application(submission: dict, run_id: str, credentials: dict | None = None) -> tuple[list, list]:
    observations, evidence = [], []
    settings = get_settings()
    target = submission["deployed_url"]
    if not public_http_url(target):
        record(observations, "deployment", "URL safety check failed", "The submitted URL did not resolve exclusively to public HTTP(S) addresses. No browser request was made.", result="failed")
        return observations, evidence

    run_dir = settings.evidence_dir / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    def add_evidence(kind: str, path, title: str, url: str, observation_id: str | None = None):
        item = {"id": f"evi-{len(evidence) + 1:03d}", "kind": kind, "title": title, "url": url, "file": path.name, "path": str(path), "observation_id": observation_id, "captured_at": stamp()}
        evidence.append(item)
        return item["id"]

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={"width": 1440, "height": 1000}, ignore_https_errors=False)
        page = await context.new_page()
        page.set_default_timeout(5000)
        page.set_default_navigation_timeout(18000)
        await page.route("**/*", lambda route: route.continue_() if public_http_url(route.request.url) else route.abort())
        page_errors, failed_responses, api_signals = [], [], []
        page.on("pageerror", lambda error: page_errors.append(str(error)[:400]))
        page.on("console", lambda msg: page_errors.append(msg.text[:400]) if msg.type == "error" else None)
        page.on("response", lambda response: failed_responses.append({"url": response.url[:700], "status": response.status}) if response.status >= 400 else None)
        page.on("request", lambda request: api_signals.append({"method": request.method, "url": request.url[:700], "resource_type": request.resource_type}) if request.resource_type in {"fetch", "xhr"} else None)
        initial_response = None
        try:
            initial_response = await page.goto(target, wait_until="domcontentloaded")
            await page.wait_for_timeout(900)
            current_url = page.url
            title = await page.title()
            visible_text = (await page.locator("body").inner_text(timeout=4000))[:12000]
            product_surface, surface_reason = classify_product_surface(current_url, title, visible_text)
            loaded = bool(initial_response and initial_response.status < 400)
            verified_product = loaded and product_surface is True
            deployment_result = "passed" if verified_product else "failed" if not loaded or product_surface is False else "needs_review"
            nav_id = record(observations, "deployment", "Participant application URL checked", f"The browser loaded {current_url}; HTTP status: {initial_response.status if initial_response else 'unknown'}. Visible text length: {len(visible_text)} characters. {surface_reason}", result=deployment_result, http_status=initial_response.status if initial_response else None, product_surface=product_surface, visible_text_length=len(visible_text))
            evidence_id = add_evidence("screenshot", run_dir / "desktop.png", "Submitted app on desktop", current_url, nav_id)
            await page.screenshot(path=str(run_dir / "desktop.png"), full_page=True, animations="disabled")
            record(observations, "page", "Page content observed", f"Visible text excerpt: {visible_text[:3200] or '(no readable body text)'}. This is browser-visible content, not an independent verification of backend behavior.", evidence_id=evidence_id)

            if not verified_product:
                return observations, evidence

            links = await page.locator("a[href]").evaluate_all("els => els.map(a => ({text:(a.innerText||a.getAttribute('aria-label')||'').trim().slice(0,100), href:a.href})).filter(x=>x.text && x.href)")
            base_origin = urlparse(current_url).netloc
            candidates = []
            seen = {current_url}
            for link in links:
                if urlparse(link["href"]).netloc == base_origin and link["href"].split("#")[0] not in seen:
                    seen.add(link["href"].split("#")[0])
                    candidates.append(link)
            record(observations, "navigation", "Navigation discovered", f"Found {len(links)} labeled link(s); {len(candidates)} unique same-origin destinations are candidates for a read-only page check.", links=links[:30])

            # Declared feature lists were removed from the intake; explore controls
            # discovered in the live app without inventing participant claims.
            features = submission.get("core_features") or []
            controls = await page.locator("button, [role=button], input[type=submit]").evaluate_all("els => els.map((e,i)=>({i,label:(e.innerText||e.value||e.getAttribute('aria-label')||'').trim().slice(0,100),disabled:!!e.disabled})).filter(x=>x.label)")
            forms = await page.locator("form").evaluate_all("els => els.map((f,i)=>({i,method:(f.method||'get').toUpperCase(),action:f.action,fields:Array.from(f.querySelectorAll('input,textarea,select')).map(e=>({type:e.type||e.tagName.toLowerCase(),name:e.name,required:!!e.required,placeholder:e.placeholder||'',label:e.labels?.[0]?.innerText||''})),submitCount:f.querySelectorAll('button[type=submit],input[type=submit],button:not([type])').length}))")
            record(observations, "controls", "Interactive controls discovered", f"Found {len(controls)} labeled button-like control(s) and {len(forms)} form(s). Labels: {', '.join(c['label'] for c in controls[:20]) or '(none)' }.", controls=controls[:40], forms=forms[:20])
            accessibility = await page.locator("input:not([type=hidden]):visible,textarea:visible,select:visible,button:visible,[role=button]:visible,img:visible").evaluate_all("els => els.map(e=>({tag:e.tagName.toLowerCase(),label:(e.getAttribute('aria-label')||e.labels?.[0]?.innerText||e.innerText||'').trim(),alt:e.getAttribute('alt'),type:e.type||''}))")
            unlabeled = [element for element in accessibility if not element["label"] and not (element["tag"] == "img" and element.get("alt") is not None)]
            record(observations, "accessibility", "Basic control labeling checked", f"Inspected {len(accessibility)} visible control/image element(s); {len(unlabeled)} had no accessible label or image alt text. This is a limited DOM check, not a full accessibility audit.", result="needs_review" if unlabeled else "passed", unlabeled=unlabeled[:20])

            for form in forms[:8]:
                if any(field.get("required") for field in form["fields"]):
                    try:
                        form_locator = page.locator("form").nth(form["i"])
                        validity = await form_locator.evaluate("f => { f.requestSubmit(); return {valid:f.checkValidity(), invalidFields:Array.from(f.querySelectorAll(':invalid')).map(e=>e.name||e.type||e.tagName)} }")
                        record(observations, "form", "Required-field validation checked", f"Submitted the empty form through native browser validation only; valid={validity['valid']}, invalid fields={validity['invalidFields']}. No valid form was submitted.", result="passed" if not validity["valid"] and validity["invalidFields"] else "needs_review")
                    except Exception as exc:
                        record(observations, "form", "Form validation could not be checked", str(exc))
                else:
                    record(observations, "form", "Form submission not attempted", "The form has no required fields. A valid submit could change external data, so this run only records its fields and controls.", result="not_tested")

            # Try one low-risk, visible control whose label overlaps a submitted feature.
            for feature in features:
                keywords = [word.lower() for word in feature.split() if len(word) >= 4]
                match = next((c for c in controls if not c["disabled"] and any(word in c["label"].lower() for word in keywords) and not any(word in c["label"].lower() for word in ("delete", "remove", "purchase", "buy", "pay", "send", "publish", "checkout", "transfer"))), None)
                if not match:
                    continue
                try:
                    button = page.locator("button, [role=button], input[type=submit]").nth(match["i"])
                    before = (await page.locator("body").inner_text())[:4000]
                    await button.click(timeout=3500)
                    await page.wait_for_timeout(450)
                    after = (await page.locator("body").inner_text())[:4000]
                    changed = before != after or page.url != current_url
                    fid = record(observations, "interaction", f"Feature control clicked: {match['label']}", f"Clicked a visible control matching the declared feature “{feature}”. URL changed: {page.url != current_url}; visible text changed: {before != after}. This action is observed; a text change alone does not prove persistence or correctness.", result="passed" if changed else "needs_review", feature=feature, button=match["label"])
                    path = run_dir / f"interaction-{len(evidence)+1}.png"
                    await page.screenshot(path=str(path), full_page=True, animations="disabled")
                    add_evidence("screenshot", path, f"After clicking {match['label']}", page.url, fid)
                    if not changed:
                        record(observations, "anti_gaming_signal", "Control had no observable response", f"The visible control “{match['label']}” produced no URL or visible text change after one click. This is a review signal, not proof that the control is fake; it may require a different input or workflow.", result="needs_review", feature=feature, related_observation=fid)
                except Exception as exc:
                    record(observations, "interaction", f"Feature control failed: {match['label']}", f"The browser could not complete the click: {str(exc)[:500]}", result="failed", feature=feature)
                break

            # Open up to three same-origin pages read-only; never follow external links.
            for link in candidates[:3]:
                try:
                    if not public_http_url(link["href"]):
                        continue
                    response = await page.goto(link["href"], wait_until="domcontentloaded", timeout=12000)
                    await page.wait_for_timeout(250)
                    text = (await page.locator("body").inner_text(timeout=3000))[:800]
                    record(observations, "navigation_test", f"Same-origin page opened: {link['text']}", f"Browser navigated to {page.url}; HTTP status {response.status if response else 'unknown'}; readable body {len(text)} characters.", result="passed" if response and response.status < 400 else "failed", linked_text=link["text"], http_status=response.status if response else None)
                except Exception as exc:
                    record(observations, "navigation_test", f"Same-origin page failed: {link['text']}", str(exc)[:500], result="failed")

            # Login is performed only when the participant supplied test credentials.
            if credentials:
                await page.goto(target, wait_until="domcontentloaded", timeout=15000)
                auth_links = await page.locator("a[href]").evaluate_all("els => els.map(a=>({text:(a.innerText||a.getAttribute('aria-label')||'').trim(),href:a.href})).filter(x=>/sign.?in|log.?in|account|auth/i.test(x.text+' '+x.href))")
                auth_target = next((item["href"] for item in auth_links if urlparse(item["href"]).netloc == urlparse(page.url).netloc and public_http_url(item["href"])), None)
                if auth_target:
                    try:
                        await page.goto(auth_target, wait_until="domcontentloaded", timeout=12000)
                        record(observations, "authentication", "Login page discovered", f"Opened same-origin authentication destination {page.url} from a visible login/account link.", result="observed")
                    except Exception as exc:
                        record(observations, "authentication", "Login page could not be opened", str(exc)[:500], result="failed")
                password = page.locator('input[type="password"]:visible').first
                if await password.count():
                    text_inputs = page.locator('input:not([type="hidden"]):not([type="password"]):not([type="submit"]):visible')
                    if await text_inputs.count():
                        await text_inputs.first.fill(credentials.get("username", ""))
                    await password.fill(credentials.get("password", ""))
                    submit = page.locator('button[type="submit"]:visible, input[type="submit"]:visible').first
                    if await submit.count():
                        login_url = page.url
                        await submit.click()
                        await page.wait_for_timeout(900)
                        login_state = await page.evaluate("({passwordVisible:!!document.querySelector('input[type=password]:not([type=hidden])'),text:(document.body.innerText||'').slice(0,1800),url:location.href})")
                        login_text = login_state["text"].lower()
                        login_failed = any(term in login_text for term in ["invalid password", "incorrect password", "invalid credentials", "login failed", "sign in failed"])
                        login_passed = (page.url != login_url or not login_state["passwordVisible"]) and not login_failed
                        login_id = record(observations, "authentication", "Demo login attempted", f"Used the submission-provided test credentials; resulting URL: {page.url}. Login form still visible: {login_state['passwordVisible']}; common error message detected: {login_failed}. A changed URL or hidden form is only a login signal and does not verify account privileges.", result="failed" if login_failed else "passed" if login_passed else "needs_review")
                        path = run_dir / "authenticated.png"
                        await page.screenshot(path=str(path), full_page=True, animations="disabled")
                        add_evidence("screenshot", path, "Result after demo login attempt", page.url, login_id)
                    else:
                        record(observations, "authentication", "Login form found without submit control", "Password field was visible, but no submit button was identified.", result="not_tested")
                else:
                    record(observations, "authentication", "No visible password field", "Demo credentials were supplied, but no password input appeared on the submitted landing page.", result="not_tested")
            else:
                record(observations, "authentication", "Authentication not tested", "No demo credentials were supplied.", result="not_tested")

            await page.set_viewport_size({"width": 390, "height": 844})
            await page.goto(target, wait_until="domcontentloaded", timeout=15000)
            await page.wait_for_timeout(300)
            layout = await page.evaluate("({width:document.documentElement.clientWidth,scrollWidth:document.documentElement.scrollWidth,bodyHeight:document.body.scrollHeight})")
            mobile_id = record(observations, "responsive", "Mobile viewport observed", f"At 390×844 CSS pixels, document client width={layout['width']}, scroll width={layout['scrollWidth']}, body height={layout['bodyHeight']}. Horizontal overflow is {layout['scrollWidth'] > layout['width']}.", result="needs_review" if layout["scrollWidth"] > layout["width"] + 4 else "passed", dimensions={"width": 390, "height": 844, **layout})
            await page.screenshot(path=str(run_dir / "mobile.png"), full_page=True, animations="disabled")
            add_evidence("screenshot", run_dir / "mobile.png", "Submitted app at mobile viewport", page.url, mobile_id)

            if page_errors:
                record(observations, "runtime_error", "Browser runtime errors observed", "; ".join(page_errors[:12]), result="failed")
            else:
                record(observations, "runtime", "No browser console errors observed", "No page errors or console error messages were emitted during this browser session.", result="passed")
            if failed_responses:
                record(observations, "network_error", "HTTP error responses observed", str(failed_responses[:15]), result="failed", responses=failed_responses[:30])
            record(observations, "network", "Network behavior observed", f"Observed {len(api_signals)} fetch/XHR request(s). Requests are signals only and do not prove correct API behavior or data persistence.", result="observed", requests=api_signals[:40])
            record(observations, "persistence", "Persistence was not independently verified", "The run did not submit a valid create/update form or reload a newly created record. A successful server-side save cannot be concluded from this browser session.", result="not_tested")
            body_lower = visible_text.lower()
            for feature in features:
                matching = [token for token in feature.lower().split() if len(token) >= 5 and token in body_lower]
                record(observations, "feature_claim", f"Declared feature checked: {feature}", f"Landing page visible text contains {len(matching)} of its substantive words ({', '.join(matching) or 'none'}). This lightweight text match is not proof the feature works.", result="observed" if matching else "needs_review", feature=feature, matching_terms=matching)
            claims_ai = bool(re.search(r"\b(ai|artificial intelligence|machine learning|llm|generative)\b", " ".join(features + [submission.get('solution_description', ''), submission.get('problem_statement', '')]).lower()))
            if claims_ai:
                record(observations, "anti_gaming_signal", "AI behavior not independently verified", "The submission claims AI behavior. This browser run did not establish whether results are generated by a live model, hardcoded, or server-side; captured request signals alone cannot prove model execution.", result="needs_review")
        except Exception as exc:
            record(observations, "deployment", "Application could not be fully inspected", f"Browser navigation or inspection failed: {str(exc)[:900]}", result="failed")
        finally:
            await context.close()
            await browser.close()
    return observations, evidence


def run_browser_judge(submission: dict, run_id: str, credentials: dict | None = None):
    return asyncio.run(inspect_application(submission, run_id, credentials))
