"""Bing wraps every result link in a bing.com/ck/a redirect.

Scout used to keep the redirect itself, so a LinkedIn search returned only
bing.com URLs, every profile was filtered out, and prospecting found nothing.
"""

import base64
from types import SimpleNamespace
from urllib.parse import quote

import pytest

from harvey.agents.scout import Scout


def bing_link(real: str) -> str:
    encoded = base64.urlsafe_b64encode(real.encode()).decode().rstrip("=")
    return f"https://www.bing.com/ck/a?!&&p=abc123&ptn=3&ver=2&u=a1{quote(encoded)}&ntb=1"


def test_unwraps_bing_redirect():
    real = "https://in.linkedin.com/in/some-founder-123"
    assert Scout._unwrap_bing_href(bing_link(real)) == real


def test_direct_links_pass_through():
    href = "https://example.com/team"
    assert Scout._unwrap_bing_href(href) == href


@pytest.mark.parametrize("href", [
    "https://www.bing.com/ck/a?!&&p=abc&ntb=1",            # no u
    "https://www.bing.com/ck/a?!&&p=abc&u=zzhttps&ntb=1",  # not a1-prefixed
    "https://www.bing.com/ck/a?!&&p=abc&u=a1%%%%&ntb=1",   # not base64
    "https://www.bing.com/ck/a?!&&p=abc&u=a1" + base64.urlsafe_b64encode(b"javascript:x").decode() + "&ntb=1",
])
def test_undecodable_redirects_come_back_unchanged(href):
    assert Scout._unwrap_bing_href(href) == href


@pytest.mark.asyncio
async def test_search_bing_returns_real_urls():
    real = "https://in.linkedin.com/in/some-founder-123"
    page = f"""
    <ol id="b_results">
      <li class="b_algo"><h2><a href="{bing_link(real)}">Some Founder</a></h2>
        <div class="b_caption"><p>Founder at a startup</p></div></li>
      <li class="b_algo"><h2><a href="https://example.com/">Direct</a></h2></li>
    </ol>"""
    scout = Scout.__new__(Scout)

    async def fake_fetch(url, **kwargs):
        return SimpleNamespace(text=page)

    scout._fetch = fake_fetch
    results = await scout._search_bing('site:linkedin.com/in "Founder"')
    assert results == [(real, "Founder at a startup"), ("https://example.com/", "")]
