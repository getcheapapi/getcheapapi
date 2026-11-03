"""Offline tests: no network, no keys, no money."""
import pytest

from getcheapapi import router
from getcheapapi.core import Stop
from getcheapapi.providers import DataForSEO, GoAnyAPI


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("GETCHEAPAPI_HOME", str(tmp_path))
    for k in ("ANYAPI_API_KEY", "GOANYAPI_API_KEY", "DATAFORSEO_LOGIN", "DATAFORSEO_PASSWORD",
              "TWITTERAPI_IO_KEY", "YIR_API_KEY"):
        monkeypatch.delenv(k, raising=False)


def test_render_required_optional_default_join():
    tpl = {"q": "$query", "gl": "$gl?", "loc": "$loc=2840", "lang": "$hl=en", "k": "$kw|join", "fixed": 10}
    out = router.render(tpl, {"query": "x", "kw": ["a", "b"], "hl": "de"})
    assert out == {"q": "x", "loc": 2840, "lang": "de", "k": "a,b", "fixed": 10}
    with pytest.raises(router.NotApplicable):
        router.render(tpl, {"kw": []})


def test_each_dedupes_and_chunk_splits():
    each = {"body": {"keyword": "$item"}, "each": "keywords"}
    assert router.bodies(each, {"keywords": ["a", "b", "a"]}) == [{"keyword": "a"}, {"keyword": "b"}]
    chunk = {"body": {"keywords": "$keywords"}, "chunk": {"field": "keywords", "size": 1000}}
    calls = router.bodies(chunk, {"keywords": [f"k{i}" for i in range(2500)]})
    assert [len(c["keywords"]) for c in calls] == [1000, 1000, 500]


def test_keyword_volume_switches_provider_by_quantity(monkeypatch):
    monkeypatch.setenv("GOANYAPI_API_KEY", "x")
    monkeypatch.setenv("DATAFORSEO_LOGIN", "x")
    monkeypatch.setenv("DATAFORSEO_PASSWORD", "x")
    cap = router.capability("keyword.volume")
    few = router.plan(cap, [{"keywords": [f"k{i}" for i in range(5)]}], {})
    many = router.plan(cap, [{"keywords": [f"k{i}" for i in range(50)]}], {})
    assert router.choose(few).provider == "goanyapi"
    assert router.choose(many).provider == "dataforseo"
    assert router.choose(many).usd == pytest.approx(0.09)


def test_keyless_routes_are_priced_but_never_chosen():
    options = router.plan(router.capability("serp.google"), [{"query": "x"}], {})
    assert all(o.status == "no key" and o.usd is not None for o in options)
    assert options[0].provider == "anyapi"  # bundled snapshot says it is cheapest
    with pytest.raises(Stop):
        router.choose(options)


def test_route_needing_missing_field_is_not_applicable(monkeypatch):
    monkeypatch.setenv("ANYAPI_API_KEY", "x")
    options = router.plan(router.capability("reddit.search"), [{"title": "x"}], {})
    assert options[0].status.startswith("n/a")


def test_price_per_multiplies_by_list_length(monkeypatch):
    monkeypatch.setenv("GOANYAPI_API_KEY", "x")
    options = router.plan(router.capability("google.trends"), [{"keywords": ["a", "b", "c"]}], {}, only="goanyapi")
    assert options[0].usd == pytest.approx(3 * GoAnyAPI.credits("google-trends") * 0.001)


def test_dataforseo_operators_cost_five_times():
    d = DataForSEO()
    plain = d.estimate("serp/google/organic/live/regular", {"keyword": "serp api", "depth": 10})
    ops = d.estimate("serp/google/organic/live/regular", {"keyword": "site:example.com serp", "depth": 10})
    assert ops == pytest.approx(5 * plain)


def test_media_batches_are_refused():
    with pytest.raises(Stop):
        router.plan(router.capability("image.generate"), [{"prompt": "a"}, {"prompt": "b"}], {})


def test_catalog_routes_reference_known_providers():
    from getcheapapi.providers import PROVIDERS
    for name, cap in router.load_catalog().items():
        assert cap["routes"], name
        for r in cap["routes"]:
            assert r["provider"] in PROVIDERS, (name, r)
            assert isinstance(r["body"], dict), (name, r)
