import base64
from urllib.parse import parse_qs, quote, urlparse


def decode_bing_redirect(href: str) -> str:
    """Bing wraps result links in bing.com/ck/a?...&u=<encoded>; unwrap it so we
    navigate straight to the real page instead of through Bing's redirector."""
    u = parse_qs(urlparse(href).query).get("u", [None])[0]
    if not u:
        return href
    raw = u[2:] if u.startswith("a1") else u
    raw += "=" * (-len(raw) % 4)
    try:
        return base64.urlsafe_b64decode(raw).decode()
    except Exception:
        return href


def fetch_snippets(query: str, user_agent: str, max_results: int = 4) -> list[dict]:
    """One-shot, incognito-equivalent browser lookup - fresh browser context,
    never persisted, closed immediately after. Returns [{"url", "text"}, ...].
    DuckDuckGo's HTML/lite endpoints 403 headless/proxied traffic outright;
    Bing serves headless requests fine, so that's the search backend here."""
    from playwright.sync_api import sync_playwright

    snippets = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context(user_agent=user_agent)
        page = context.new_page()
        try:
            page.goto(f"https://www.bing.com/search?q={quote(query)}", timeout=15000)
            hrefs = page.eval_on_selector_all(
                "li.b_algo h2 a",
                f"els => els.slice(0, {max_results}).map(e => e.href)",
            )
            for href in hrefs:
                url = decode_bing_redirect(href)
                try:
                    page.goto(url, timeout=10000)
                    snippets.append({"url": url, "text": page.inner_text("body")[:3000]})
                except Exception:
                    continue
        finally:
            context.close()
            browser.close()
    return snippets
