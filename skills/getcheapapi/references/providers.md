# Provider notes

Prices as of 2026-11. The charge in each response and each provider's pricing page are authoritative; `getcheapapi prices refresh` updates the local cache from the providers that publish prices.

## Same data, several routes (measured 2026-11)

| Need | Routes and total | Verdict |
|---|---|---|
| Google top 100 | anyapi `google.search` paged 10 times ≈ $0.005; dataforseo `serp/google/organic/task_post` for 100 results ≈ $0.006 (priced per 10 results, queued); anyapi `google.search_100` $0.024 | Page `google.search`. The cheap source returns about 10 results even with `limit:100`; follow `nextCursor` (page 2 is results 11–20). |
| Google Trends | anyapi `google.trends` $0.002 (one other source charges $0.018); goanyapi `google-trends` 6 credits per keyword, empty results charged | anyapi; when the cheap source refuses, stop and quote rather than allow the $0.018 one |
| Search volume, keyword ideas, backlinks | dataforseo batch endpoints; anyapi `seo.*` is DataForSEO data resold at about +20% with no batching | dataforseo (goanyapi for a handful of keywords) |
| Bing top 10 | anyapi `bing.search` $0.00085; `brave.search` $0.00085 is a different engine with different results | `bing.search` for Bing results |

A real overspend these rules prevent: search volumes split into 15 calls at $0.108 when one call takes 1,000 keywords, backlinks fetched one domain at a time at $0.029 each, and a script that kept sending 211 requests after a 402.

## AnyAPI (getanyapi.com)

- `POST https://api.getanyapi.com/v1/run/{sku}`, header `X-API-Key`. Returns `output` (`{found, data}`), `costUsd`, `items`; `found:false` is a normal "nothing found", not a failure.
- Catalog: `GET /v1/apis`; one SKU: `GET /v1/apis/{sku}` with `inputSchema` and `pricing` (`from.baseUsd`, `perUnitUsd`, `failoverMaxUsd`).
- Sources: `GET /v1/apis/{sku}` lists `lanes[]`, each with `source.id`, price and the `fields` it returns. Sending `source` (an ordered list) with `allowFallbacks:false` restricts serving to those sources; when none can serve, the request is refused with no charge, and the response's `source.id` names who served. Without it, the cheapest source serves first and failures fail over to others at their prices (up to 6x on `tiktok.search_keyword`, 28x on `twitter.search`). getcheapapi always pins.
- Free quote: `POST /v1/apis/{sku}/quote` with the same input returns `minCostUsd`, `maxCostUsd` and `exact` without running; pinned requests quote exactly.
- No batch endpoints: one input per call.
- Async SKUs return `requestId` and `nextAction`: poll `GET /v1/requests/{id}`; resubmitting charges again.
- Call history: `GET /v1/requests?limit=100&before=<nextCursor>` (the paging parameter is `before`). Usage by endpoint: `GET /v1/usage` (last 30 days); a mean price well above an endpoint's cheapest source means calls that bypassed pinning.
- Search SKUs:

| SKU | Per page | Result list | Key parameters |
|---|---|---|---|
| `twitter.search` | ~20, with `nextCursor` | `data.items` | `query` (X advanced search syntax), `queryType`: Latest/Top/Photos/Videos, `cursor` |
| `reddit.search` | 25; the cheapest source returns **no** `nextCursor` | `data.posts` | `query` (`subreddit:`, `author:`, `title:`, AND/OR/NOT), `sort`, `timeframe`, `cursor` |
| `tiktok.search_keyword` | 19–20, with `nextCursor` | `data.videos` | `query`, `sortBy`, `datePosted`: 0/1/7/30/90/180, `cursor` |

- Price-raising options:
  - `requireFields`: routes to pricier sources that return the field. Reddit pages only with `["nextCursor"]`, which makes every page $0.80 per 1,000, 2.3x a first page. For a few more Reddit results, take more first pages with other `sort`, `timeframe` or `subreddit:` values.
  - `requireSinglePage` on `twitter.search`: routes to a per-item source, dearer than paging.
  - `preferLatencyUnderMs`: prefers faster, dearer sources.
- X query syntax: bare words are ANDed. Use `A OR B` for either; wrap it when other operators follow, e.g. `(A OR B) -filter:replies`.
- `seo.*` SKUs resell DataForSEO at about +20% without batching; use DataForSEO directly.

## DataForSEO (dataforseo.com)

- Basic auth (`DATAFORSEO_LOGIN:DATAFORSEO_PASSWORD`). `POST https://api.dataforseo.com/v3/<path>` with an array of tasks; getcheapapi sends one task and wraps it.
- Response: top-level `cost`; task results in `tasks[].status_code` and `tasks[].result[]`. 20000 is success; 40200 and 40210 mean out of balance (exit code 2).
- Queued mode (`task_post`) is cheaper but two-step: post, keep `tasks[].id`, then collect with `.../task_get/advanced/<id>` minutes to hours later (collecting is free; getcheapapi uses GET for `task_get` paths). `/live` answers at once for 1.5–3x the price and is limited to 12 calls per minute per account.
- Prices:
  - Google Ads search volume: $0.06 queued, $0.09 live, per call of up to 1,000 keywords.
  - Labs (suggestions, ideas, ranked keywords): live only, $0.012 per call + $0.00012 per result.
  - Backlinks (summary, bulk_ranks, bulk_referring_domains…): live only, $0.024 per call + $0.000036 per row; bulk endpoints take up to 1,000 targets.
  - Google organic SERP: per 10 results, $0.0006 queued, $0.0012 priority, $0.002 live; queries with search operators cost 5x.
- Minimum top-up $50, balance does not expire, no subscription. New accounts get $1 of trial credit; a first call may return 403 `40104` until the account is verified in app.dataforseo.com.

## twitterapi.io (read only)

- `GET https://api.twitterapi.io/<path>`, header `X-API-Key`; balance at `oapi/my/info`.
- Billing: $1 = 100,000 credits. Posts are charged per returned item at 15 credits ($0.00015), **at least 15 credits per call even when empty**. One profile 18 credits; profiles in batches of 100+ are 1 credit each. Followers 1–3 credits each; follower IDs in batches of 4,000+ cost 0.45 credits each.
- Responses carry no cost field; getcheapapi estimates from returned items.
- Purchased credits do not expire; bonus credits expire after 31 days. Paid accounts are limited to 20 requests per second.
- Posting, DMs, follows, logins and monitoring are out of scope; getcheapapi refuses those paths.

## GoAnyAPI (goanyapi.com)

- `GET https://api.goanyapi.com/api/v1/<id>?params`, header `Authorization: Bearer`. Unknown parameters are rejected. Catalog with prices (no key): `/api/v1/mcp/catalog`; charge history: `/api/v1/activity-credits`.
- Charges are exact; failures and empty results are free, except `google-trends`, which charges empty results. $10 buys 10,000 credits.
- Credits per call (the catalog's `pricing` wins when present): `backlink` 4, `dr` 2, `dr-history` 2 per month returned (`includeDr=false` previews free), `traffic` 2–6, `keyword-difficulty` and `keyword-generator` 3, `keyword-suggestions` 1 per page of 10 (no volumes), `keyword-search-volume` 3 per keyword, `serp-stable` 1, `serp-standard` 2, `serp` 3, `bing-serp` 2, `google-intitle` and `google-site-search` 4, `google-trends` 6 per keyword, `transparency` 4. The three Google SERP editions take different parameters (`serp-stable` uses `query`, the others `q`).
- Data caveat: `backlink`'s `dofollowBacklinks` and `dofollowRefdomains` count only the 20 highlighted backlinks it returns, not the whole site; totals and DR look like a free backlink checker's and can differ from DataForSEO by 40%.

## Yir (yir.ai)

- Image, video, audio and 3D generation through one key; Yir routes each model to its cheapest available channel.
- `POST /v1/{images|videos|audio}/quotes` prices a request without creating a job and returns the official price for comparison; getcheapapi quotes before every job and caps it server-side with `max_cost` at the quote + 10%.
- Jobs are asynchronous; getcheapapi waits for a terminal state and downloads the files. The charge is final when `billing.status` is `settled`.
- Each file carries `fidelity.grade`; only `original` is the model's native output. Ask for `{"fidelity":"original"}` in `routing` when results will be shown as that model's work (it may cost more).
- The gateway occasionally returns 5xx; quotes are retried, jobs are not.
