"""Company search mines list pages instead of treating them as companies.

A search for "startup India" companies mostly returns pages about companies —
Failory's India startups page, a YC portfolio filter, topstartups.io, a
government programme, a journal PDF. Scout used to store each of those as the
company and look for its founders, so it found no one to email.
"""

from types import SimpleNamespace

import pytest
import pytest_asyncio

from harvey.agents import scout as scout_module
from harvey.agents.scout import Scout
from harvey.models.company import Company
from harvey.state import StateManager

LIST_PAGES = [
    ("https://www.failory.com/startups/india", "Learn from startup failures"),
    ("https://topstartups.io/?hq_location=India", "Startups hiring now"),
    ("https://www.ycombinator.com/companies/location/india", "Y Combinator"),
    ("https://indiaai.gov.in/startup", "An umbrella programme"),
    ("https://www.iitb.ac.in/en/incubator", "Incubated ventures"),
    ("https://inc42.com/features/top-50-fintech-startups/", "Top 50 fintech startups"),
    ("https://example.org/research", "International Journal of Novel Research"),
]

COMPANY_SITES = [
    ("https://razorpay.com/", "Razorpay is India's leading payments solution"),
    ("https://acme.in/about", "We help small businesses with bookkeeping"),
    ("https://kuvera.in/blog/sip", "Plan your SIPs"),
    ("https://bookkeep.ac/", "Bookkeeping for freelancers"),
]


@pytest.mark.parametrize("url,snippet", LIST_PAGES)
def test_list_pages_are_recognised(url, snippet):
    assert Scout._looks_like_list_page(url, snippet)


@pytest.mark.parametrize("url,snippet", COMPANY_SITES)
def test_company_sites_are_not_mistaken_for_lists(url, snippet):
    assert not Scout._looks_like_list_page(url, snippet)


def test_documents_are_recognised():
    assert Scout._is_document_url("https://www.ijnrd.org/papers/IJNRD2208164.pdf")
    assert not Scout._is_document_url("https://razorpay.com/")


ICP = SimpleNamespace(
    industries=["startup"], geography=["India"], titles=["Founder"],
    company_size="1-20 employees",
)

DIRECTORY_HTML = """
<a href="https://www.failory.com/blog">Our blog</a>
<a href="https://tinyledger.in/">TinyLedger</a>
<a href="https://linkedin.com/company/x">LinkedIn</a>
<a href="https://startupindia.gov.in/">Startup India</a>
<a href="https://forms.gle/AbC123">Apply here</a>
<a href="https://ind01.safelinks.protection.outlook.com/?url=x">A link</a>
<a href="https://gsc.bigco.com/">Big Co tool</a>
<a href="https://cashflowkit.io/">CashflowKit</a>
"""


@pytest.mark.parametrize("domain", [
    "forms.gle", "ind01.safelinks.protection.outlook.com", "forms.cloud.microsoft",
    "gsc.cars24.com", "docs.google.com", "co.in",
])
def test_tool_redirect_and_subdomain_hosts_are_not_company_sites(domain):
    assert not Scout._is_site_root(domain)


@pytest.mark.parametrize("domain", [
    "8arms.ai", "rupeek.com", "acme.co.in", "acme.co", "www.razorpay.com",
    "acme.com.au", "formspree.io",
])
def test_bare_company_domains_are_site_roots(domain):
    assert Scout._is_site_root(domain)


@pytest_asyncio.fixture
async def state(tmp_path):
    state = StateManager(str(tmp_path / "l.db"))
    await state.init_db()
    return state


@pytest.fixture(autouse=True)
def _no_search_delay(monkeypatch):
    monkeypatch.setattr(scout_module, "SEARCH_DELAY", (0, 0))


def scout_with(state, results):
    scout = Scout(None, state, SimpleNamespace(icp=ICP), SimpleNamespace(serper_api_key=""))
    scraped = []

    async def search(query):
        return results

    async def nothing(query):
        return []

    async def fetch(url, **kwargs):
        return SimpleNamespace(text=DIRECTORY_HTML)

    async def company_info(domain):
        scraped.append(domain)
        return {"name": domain, "website": f"https://{domain}"}

    scout._search_duckduckgo = search
    scout._search_bing = nothing
    scout._search_google = nothing
    scout._fetch = fetch
    scout._scrape_company_info = company_info
    scout.scraped = scraped
    return scout


@pytest.mark.asyncio
async def test_a_list_page_yields_the_companies_it_links_to(state):
    scout = scout_with(state, [
        ("https://www.failory.com/startups/india", "Indian startups"),
        ("https://razorpay.com/", "Payments for India"),
    ])
    companies = await scout._find_companies_via_search()
    domains = [c["domain"] for c in companies]

    # The linked companies, minus the list site itself, social links and a
    # government site; then the real company hit, scraped as before.
    assert domains == ["tinyledger.in", "cashflowkit.io", "razorpay.com"]
    assert scout.scraped == ["razorpay.com"]


@pytest.mark.asyncio
async def test_a_document_hit_is_skipped(state):
    scout = scout_with(state, [("https://www.ijnrd.org/papers/IJNRD2208164.pdf", "A paper")])
    assert await scout._find_companies_via_search() == []
    assert scout.scraped == []


@pytest.mark.asyncio
async def test_a_list_site_stored_as_a_company_earlier_is_still_mined(state):
    await state.add_company(Company(name="Failory", domain="failory.com"))
    scout = scout_with(state, [("https://www.failory.com/startups/india", "Indian startups")])
    domains = [c["domain"] for c in await scout._find_companies_via_search()]
    assert domains == ["tinyledger.in", "cashflowkit.io"]
