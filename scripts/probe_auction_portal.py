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
        for anchor in page.locator("a").all():
            href = anchor.get_attribute("href") or ""
            label = (anchor.inner_text() or "").strip()[:100]
            if href and any(word in (label + " " + href).lower() for word in ("pdf", "download", "subasta", "auction")):
                links.append({"label": label, "url": safe_url(urljoin(page.url, href))})

        buttons = [
            (button.inner_text() or "").strip()[:100]
            for button in page.locator("button").all()
            if button.is_visible() and (button.inner_text() or "").strip()
        ]
        report = {
            "final_url": safe_url(page.url),
            "title": page.title(),
            "password_field_visible": bool(first_visible(page, ["input[type=password]"])),
            "blocked_terms": blocked_terms,
            "candidate_links": links[:30],
            "visible_buttons": buttons[:30],
        }
        print(json.dumps(report, indent=2))
        if report["password_field_visible"] or blocked_terms:
            raise RuntimeError("Portal authentication did not reach the downloads page")
        browser.close()


if __name__ == "__main__":
    main()
