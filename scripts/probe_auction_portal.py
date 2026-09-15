"""Credential-safe probe of the ACP auction information download page."""

from __future__ import annotations

import json
import os
from urllib.parse import urljoin, urlsplit, urlunsplit

from playwright.sync_api import sync_playwright


START_URL = "https://auctioninfo.pancanal.com/en/pdfs"


def safe_url(url: str) -> str:
    """Retain route information but never log queries, fragments, or credentials."""
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.hostname or "", parts.path, "", ""))


def first_visible(page, selectors):
    for selector in selectors:
        locator = page.locator(selector)
        for index in range(locator.count()):
            candidate = locator.nth(index)
            if candidate.is_visible():
                return candidate
    return None


def main() -> None:
    email = os.environ["ACP_AUCTION_EMAIL"]
    password = os.environ["ACP_AUCTION_PASSWORD"]

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(accept_downloads=True)
        page = context.new_page()
        responses = []

        def record_response(response):
            content_type = (response.headers.get("content-type") or "").split(";", 1)[0]
            path = safe_url(response.url)
            interesting = (
                content_type in {"application/pdf", "application/json"}
                or any(term in path.lower() for term in ("pdf", "download", "auction", "subasta", "tableau", "bootstrap"))
            )
            if interesting:
                responses.append({"status": response.status, "content_type": content_type, "url": path})

        page.on("response", record_response)
        page.goto(START_URL, wait_until="domcontentloaded", timeout=60_000)

        password_box = first_visible(page, ["input[type=password]"])
        if password_box:
            email_box = first_visible(page, [
                "input[type=email]",
                "input[name*=email i]",
                "input[name*=user i]",
                "input[type=text]",
            ])
            if not email_box:
                raise RuntimeError("Login page has a password field but no identifiable username field")
            email_box.fill(email)
            password_box.fill(password)
            submit = first_visible(page, [
                "button[type=submit]",
                "input[type=submit]",
                "button:has-text('Log in')",
                "button:has-text('Login')",
                "button:has-text('Sign in')",
            ])
            if not submit:
                raise RuntimeError("Login page has no identifiable submit control")
            submit.click()
            page.wait_for_load_state("domcontentloaded", timeout=60_000)
            page.wait_for_timeout(3_000)

        if safe_url(page.url) != START_URL:
            page.goto(START_URL, wait_until="domcontentloaded", timeout=60_000)
            page.wait_for_timeout(3_000)

        body_text = page.locator("body").inner_text().lower()
        blocked_terms = [term for term in ("invalid password", "incorrect password", "captcha", "verification code", "two-factor") if term in body_text]
        links = []
        buttons = []
        frames = []
        for frame in page.frames:
            frame_url = safe_url(frame.url)
            frames.append({"name": frame.name[:80], "url": frame_url})
            try:
                for anchor in frame.locator("a").all():
                    href = anchor.get_attribute("href") or ""
                    label = (anchor.inner_text() or "").strip()[:100]
                    if href and any(word in (label + " " + href).lower() for word in ("pdf", "download", "subasta", "auction")):
                        links.append({"label": label, "url": safe_url(urljoin(frame.url, href))})
                buttons.extend(
                    (button.inner_text() or button.get_attribute("aria-label") or "").strip()[:100]
                    for button in frame.locator("button, [role=button]").all()
                    if button.is_visible()
                    and (button.inner_text() or button.get_attribute("aria-label") or "").strip()
                )
            except Exception as exc:
                frames[-1]["inspection_error"] = type(exc).__name__
        report = {
            "final_url": safe_url(page.url),
            "title": page.title(),
            "password_field_visible": bool(first_visible(page, ["input[type=password]"])),
            "blocked_terms": blocked_terms,
            "frames": frames,
            "candidate_links": links[:30],
            "visible_buttons": buttons[:30],
            "interesting_responses": list({json.dumps(item, sort_keys=True): item for item in responses}.values())[-50:],
        }
        print(json.dumps(report, indent=2))
        if report["password_field_visible"] or blocked_terms:
            raise RuntimeError("Portal authentication did not reach the downloads page")
        browser.close()


if __name__ == "__main__":
    main()
