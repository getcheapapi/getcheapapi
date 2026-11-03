# getcheapapi

**Stop overpaying for data and media APIs.** getcheapapi is an open-source price router for AI agents and developers: it prices every provider you can use for a call, runs it through the cheapest one, and refuses to overspend.

Website: [getcheapapi.com](https://getcheapapi.com)

```text
$ getcheapapi quote keyword.volume --input '{"keywords":["k1","k2","k3","k4","k5"]}'
  goanyapi keyword-search-volume                    $0.01500   x1.0  5 calls   ok
  dataforseo keywords_data/google_ads/search_volume/live  $0.09000   x6.0  1 call    ok
would run: goanyapi keyword-search-volume $0.01500

$ getcheapapi quote keyword.volume --input @50-keywords.json
  dataforseo keywords_data/google_ads/search_volume/live  $0.09000   x1.0  1 call    ok
  goanyapi keyword-search-volume                    $0.15000   x1.7  50 calls  ok
would run: dataforseo keywords_data/google_ads/search_volume/live $0.09000
```

## Why

The same data costs 2x to 200x more depending on the route, and the default is usually the expensive one:

- **Aggregators fail over to dearer upstreams silently.** One AnyAPI endpoint is served by several sources whose prices differ by up to 28x (X search) or 200x; when the cheap one fails, the default retry bills the dear one.
- **Harmless-looking options raise the price.** A field that only some sources return, a "live" mode, a search operator (5x on DataForSEO SERP).
- **Billing rules differ everywhere.** Per call, per row, per keyword; empty results charged on some, free on others; batch endpoints that take 1,000 items for one price.
- **Agents have no brakes.** A real night: keyword volumes split into 15 calls instead of one, backlinks fetched domain by domain, and a script that kept sending 211 requests after a 402.

getcheapapi turns that knowledge into code: a capability catalog, a local price cache, and guards on every paid call.

## What it does

- **Ask for a capability, not a provider**: `serp.google`, `x.search`, `keyword.volume`, `image.generate`… Each maps to routes across providers, with field mapping and batching.
- **Prices every route** from a local cache (live price APIs where providers have them, published tables where they do not) and picks the cheapest one you have a key for. Routes you have no key for are priced too, so you see what another key would save.
- **Re-prices on fresh prices before spending**, pins AnyAPI to the cheapest sources with failover off, and keeps a price baseline that stops the run when the cheapest price jumps.
- **Guards every run**: estimate first and refuse past `--max-usd`; stop on 402 (exit code 2) or the first failure; dedupe and batch inputs; save every response; log every call to a local ledger (`getcheapapi spend`).
- **Media too**: image, video and speech generation via Yir, quoted before every job and capped server-side.

Out of scope: LLM text routing (LiteLLM and OpenRouter cover it), and any write action on social accounts.

## Providers

| Provider | Used for | Pricing source |
|---|---|---|
| [AnyAPI](https://getanyapi.com/?via=q89thkytbw) | SERP, X, Reddit, TikTok, Google Trends | live per-source prices |
| [DataForSEO](https://dataforseo.com) | keyword volume and ideas, backlinks, SERP | published price list |
| [GoAnyAPI](https://goanyapi.com/r/ga-ccef6a6e4f) | SERP, DR, traffic, keyword volume, backlinks | public catalog |
| [twitterapi.io](https://twitterapi.io/?ref=wn7a9fzv) | X search (read only) | published price list |
| [Yir](https://yir.ai) | image, video, speech generation | live quotes |

Some provider links above carry our referral code, and the CLI prints them when a key is missing. They never affect routing: routes are ranked by price only.

## Install

```bash
pip install git+https://github.com/getcheapapi/getcheapapi   # a PyPI release is coming
cp .env.example .env   # from a clone; fill in the keys you have, one is enough
getcheapapi caps -v
```

For agents (Claude Code, Codex and others), install the skill in [`skills/getcheapapi`](skills/getcheapapi/SKILL.md): link or copy that folder into your agent's skills directory (for example `~/.claude/skills/getcheapapi`). Linked from a clone, it runs without installing the package.

## Usage

```bash
getcheapapi caps -v                                   # capabilities, inputs, examples
getcheapapi quote serp.google --input '{"query":"cheap serp api"}'   # compare, spends nothing
getcheapapi run serp.google --input '{"query":"cheap serp api"}' --max-usd 0.01
getcheapapi run x.search --input '[{"query":"a"},{"query":"b"}]'      # a list runs as one batch
getcheapapi call dataforseo backlinks/summary/live --input '{"target":"example.com"}'  # raw endpoint, same guards
getcheapapi prices refresh                            # update the local price cache
getcheapapi spend --days 7                            # what you spent, by provider and endpoint
getcheapapi balance anyapi
```

State lives in `~/.getcheapapi/` (override with `GETCHEAPAPI_HOME`): price cache, price baseline, ledger, saved results. Nothing leaves your machine except the API calls themselves.

## Contributing

Prices and endpoints change. To add or fix a route, edit `src/getcheapapi/data/catalog.json`, then:

```bash
python scripts/check_catalog.py   # checks route fields against live provider schemas (free)
python -m pytest
```

## Disclosure

getcheapapi is neutral by design: routes are ranked by price only. If the maintainers ever list a service of their own, it will be labeled as such and ranked by the same rule.

## License

MIT
