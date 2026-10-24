"""Scout's web searches are split by strategy and rotate through the ICP.

Profile search used to run first against one shared pool of three queries,
spend all of them, and leave company discovery — the only search path that
ends in an email address — with none. It also always searched the first
three titles in the first city, so after one cycle it found nobody new.
"""

from types import SimpleNamespace

import pytest
import pytest_asyncio

from harvey.agents import scout as scout_module
from harvey.agents.scout import SEARCH_BUDGET, Scout
from harvey.state import StateManager

ICP = SimpleNamespace(
    industries=["startup", "SaaS"],
    geography=["Mumbai", "Pune"],
    titles=["Founder", "CEO", "Owner"],
    company_size="1-20 employees",
)


@pytest_asyncio.fixture
async def state(tmp_path):
    state = StateManager(str(tmp_path / "s.db"))
    await state.init_db()
    return state


@pytest.fixture(autouse=True)
def _no_search_delay(monkeypatch):
    monkeypatch.setattr(scout_module, "SEARCH_DELAY", (0, 0))


def new_cycle(state, queries):
    """A Scout at the start of a cycle whose search engines record queries."""
    scout = Scout(None, state, SimpleNamespace(icp=ICP), SimpleNamespace(serper_api_key=""))

    async def record(query):
        queries.append(query)
        return []

    async def nothing(query):
        return []

    scout._search_duckduckgo = record
    scout._search_bing = nothing
    scout._search_google = nothing
    return scout


@pytest.mark.asyncio
async def test_profile_search_leaves_company_discovery_its_own_queries(state):
    queries = []
    scout = new_cycle(state, queries)
    await scout._prospect_via_profile_search()
    await scout._find_companies_via_search()

    profile = [q for q in queries if q.startswith("site:linkedin.com/in")]
    company = [q for q in queries if not q.startswith("site:linkedin.com/in")]
    assert len(profile) == SEARCH_BUDGET["profile"]
    assert len(company) == SEARCH_BUDGET["company"]


@pytest.mark.asyncio
async def test_profile_search_walks_titles_then_cities(state):
    queries = []
    for _ in range(4):
        await new_cycle(state, queries)._prospect_via_profile_search()

    assert queries == [
        'site:linkedin.com/in "Founder" "startup" "Mumbai"',
        'site:linkedin.com/in "CEO" "startup" "Mumbai"',
        'site:linkedin.com/in "Owner" "startup" "Mumbai"',
        'site:linkedin.com/in "Founder" "startup" "Pune"',
    ]


@pytest.mark.asyncio
async def test_profile_rotation_wraps_around_to_the_start(state):
    queries = []
    combos = len(ICP.industries) * len(ICP.geography) * len(ICP.titles)
    for _ in range(combos + 1):
        await new_cycle(state, queries)._prospect_via_profile_search()

    assert len(set(queries)) == combos
    assert queries[combos] == queries[0]


@pytest.mark.asyncio
async def test_company_search_moves_on_to_new_industries_and_cities(state):
    queries = []
    seen_per_cycle = []
    for _ in range(4):
        before = len(queries)
        await new_cycle(state, queries)._find_companies_via_search()
        seen_per_cycle.append(queries[before:])

    assert all(len(cycle) == SEARCH_BUDGET["company"] for cycle in seen_per_cycle)
    assert len(set(queries)) == len(queries)
    assert '"startup" "Mumbai" "1-20 employees" company' in queries
    assert '"startup" "Pune" "1-20 employees" company' in queries
    assert '"SaaS" "Mumbai" "1-20 employees" company' in queries
