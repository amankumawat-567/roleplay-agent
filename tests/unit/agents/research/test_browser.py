import base64

from roleplay_agent.agents.research.browser import decode_bing_redirect


def test_decode_bing_redirect_passes_through_url_without_u_param():
    href = "https://www.bing.com/ck/a?ping=xyz"
    assert decode_bing_redirect(href) == href


def test_decode_bing_redirect_decodes_wrapped_url():
    target = "https://real-site.com/article"
    encoded = base64.urlsafe_b64encode(target.encode()).decode().rstrip("=")
    href = f"https://www.bing.com/ck/a?ping=xyz&u=a1{encoded}"
    assert decode_bing_redirect(href) == target
