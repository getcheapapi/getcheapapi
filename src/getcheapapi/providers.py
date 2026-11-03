"""One adapter per upstream. Each knows its keys, how to price a call before making it, and how to call.

estimate(endpoint, body, fresh) -> USD upper bound for one call (fresh=False may read the price cache)
prepare(endpoint, body)        -> body to send (AnyAPI pins sources, Yir adds max_cost); may raise Stop
call(endpoint, body)           -> (raw result, charged USD, rows returned, ok)
"""
from __future__ import annotations

import base64
import os
import time
import urllib.parse
import uuid
from pathlib import Path

from getcheapapi import lanes as L
from getcheapapi.core import EXIT_NO_BALANCE, Stop, env, has_env, home, http, list_len, now, read_json, write_json

DAY = 86400
DATA_DIR = Path(__file__).resolve().parent / "data"


def snapshot(provider: str) -> dict:
    """Bundled cheapest-price snapshot {endpoint: usd}, used to compare providers the user has no key for."""
    return read_json(DATA_DIR / "prices.json", {}).get(provider, {})


class Provider:
    name = ""
    keys: tuple[str, ...] = ()
    site = ""

    @classmethod
    def configured(cls) -> bool:
        return has_env(*cls.keys)

    def prepare(self, endpoint: str, body: dict) -> dict:
        return body

    def estimate(self, endpoint: str, body: dict, fresh: bool = True) -> float:
        raise NotImplementedError

    def call(self, endpoint: str, body: dict):
        raise NotImplementedError


class AnyAPI(Provider):
    name, keys, site = "anyapi", ("ANYAPI_API_KEY",), "https://getanyapi.com"
    base = L.BASE

    def __init__(self, max_ratio: float = L.DEFAULT_MAX_RATIO):
        self.max_ratio = max_ratio
        self._pinned: dict[int, tuple[set, float]] = {}  # id(pinned body) -> (allowed sources, max price)

    def prepare(self, endpoint, body):
        """Pin to the cheap sources on fresh prices; refuse before any spend when only dearer ones fit."""
        try:
            pinned, allowed, price = L.pin(endpoint, body, L.fetch_lanes(endpoint, self.key), self.max_ratio)
        except L.PricierOnly as exc:
            hint = "" if isinstance(exc, L.PriceRose) else "(--max-ratio N raises the ratio.) "
            raise Stop(f"{exc}\n{hint}Show the user this table and wait for their decision.") from None
        self._pinned[id(pinned)] = (allowed, price)
        return pinned

    @property
    def key(self) -> str:
        return env("ANYAPI_API_KEY")

    def estimate(self, endpoint, body, fresh=True):
        if id(body) in self._pinned:
            return self._pinned[id(body)][1]
        if not self.configured():  # compare without a key: the bundled snapshot of cheapest prices
            price = snapshot("anyapi").get(endpoint)
            if price is None:
                raise Stop(f"anyapi {endpoint}: no key and no snapshot price")
            return float(price)
        return L.cheapest(L.fetch_lanes(endpoint, self.key, 0 if fresh else DAY), body)

    def call(self, endpoint, body):
        allowed, price = self._pinned[id(body)]
        try:
            result = http("POST", f"{self.base}/run/{endpoint}", {"X-API-Key": self.key}, body)
        except Stop as exc:
            if exc.code == EXIT_NO_BALANCE:
                raise
            raise Stop(f"{exc}\nThe pinned cheap sources {sorted(allowed)} cannot serve it now (no charge); "
                       f"others cost more:\n{L.price_table(endpoint, body, L.fetch_lanes(endpoint, self.key))}\n"
                       "Ask the user before rerunning with --max-ratio N.") from None
        problem = L.served_ok(result, allowed, price)
        if problem:
            raise Stop(f"AnyAPI {endpoint} {problem}; stopping.")
        output = result.get("output") or {}
        return result, float(result.get("costUsd") or 0), list_len(output.get("data")), True

    def balance(self):
        return http("GET", f"{self.base}/balance", {"X-API-Key": self.key})


# GoAnyAPI credits per successful call, used when its catalog gives no price (2026-11). $10 = 10,000 credits.
GOANY_CREDITS = {"backlink": 4, "dr": 2, "traffic": 6, "keyword-difficulty": 3, "keyword-generator": 3,
                 "keyword-suggestions": 1, "keyword-search-volume": 3, "serp": 3, "serp-standard": 2,
                 "serp-stable": 1, "bing-serp": 2, "google-intitle": 4, "google-site-search": 4,
                 "google-trends": 6, "transparency": 4, "adsense": 3, "ads-statistics": 5,
                 "html-to-markdown-api": 1}
GOANY_USD_PER_CREDIT = 0.001


class GoAnyAPI(Provider):
    name, keys, site = "goanyapi", ("GOANYAPI_API_KEY",), "https://goanyapi.com"
    base = "https://api.goanyapi.com/api/v1"

    @property
    def key(self) -> str:
        return env("GOANYAPI_API_KEY")

    @staticmethod
    def credits(endpoint: str) -> int:
        cached = read_json(home() / "prices" / "goanyapi.json", {}).get("credits", {})
        return int(cached.get(endpoint) or GOANY_CREDITS.get(endpoint, 6))

    @classmethod
    def refresh_prices(cls) -> dict:
        """Fixed-credit prices from the public catalog (no key needed), merged over the built-in table."""
        apis = http("GET", f"{cls.base}/mcp/catalog", {}, timeout=60)["data"]["apis"]
        credits = dict(GOANY_CREDITS)
        for a in apis:
            p = a.get("pricing") or {}
            if p.get("kind") == "fixed" and p.get("credits") is not None:
                credits[a["id"]] = int(p["credits"])
            elif p.get("kind") == "free":
                credits[a["id"]] = 0
        write_json(home() / "prices" / "goanyapi.json", {"at": now(), "credits": credits})
        return credits

    def estimate(self, endpoint, body, fresh=True):
        return self.credits(endpoint) * GOANY_USD_PER_CREDIT

    def call(self, endpoint, body):
        query = urllib.parse.urlencode(body)
        result = http("GET", f"{self.base}/{endpoint}?{query}", {"Authorization": f"Bearer {self.key}"})
        data = result.get("data") if isinstance(result.get("data"), dict) else {}
        return result, float(data.get("costCredits") or 0) * GOANY_USD_PER_CREDIT, list_len(data), True

    def balance(self):
        return http("GET", f"{self.base}/credits/balance", {"Authorization": f"Bearer {self.key}"})


class DataForSEO(Provider):
    name, keys, site = "dataforseo", ("DATAFORSEO_LOGIN", "DATAFORSEO_PASSWORD"), "https://dataforseo.com"
    base = "https://api.dataforseo.com/v3"

    @property
    def auth(self) -> dict:
        token = base64.b64encode(f"{env('DATAFORSEO_LOGIN')}:{env('DATAFORSEO_PASSWORD')}".encode()).decode()
        return {"Authorization": f"Basic {token}"}

    def estimate(self, endpoint, body, fresh=True):
        """Published prices (2026-11); DataForSEO has no quote API."""
        limit = int(body.get("limit") or 100)
        if "task_get" in endpoint or "tasks_ready" in endpoint:
            return 0.0  # collecting a queued task is free; the charge was taken at task_post
        if endpoint.startswith("keywords_data/google_ads/"):
            return 0.09 if endpoint.endswith("/live") else 0.06
        if endpoint.startswith("backlinks/"):
            rows = len(body.get("targets") or []) or limit
            return 0.024 + 0.000036 * rows
        if endpoint.startswith("dataforseo_labs/"):
            return 0.012 + 0.00012 * limit
        if endpoint.startswith("serp/"):
            pages = max(1, int(body.get("depth") or 10) // 10)
            live = "/live/" in endpoint
            per_page = 0.002 if live else 0.0006
            ops = any(op in str(body.get("keyword", "")) for op in ("site:", "intitle:", "inurl:", "allinurl:"))
            return per_page * pages * (5 if ops else 1)
        return 0.05

    def call(self, endpoint, body):
        collect = "task_get" in endpoint or "tasks_ready" in endpoint
        result = http("GET" if collect else "POST", f"{self.base}/{endpoint}", self.auth, None if collect else [body])
        if result.get("status_code") in (40200, 40210):
            raise Stop(f"DataForSEO {result.get('status_code')}: {result.get('status_message')}", EXIT_NO_BALANCE)
        task = (result.get("tasks") or [{}])[0]
        ok = task.get("status_code", 0) < 40000
        if not ok and task.get("status_code") in (40200, 40210):
            raise Stop(f"DataForSEO {task['status_code']}: {task.get('status_message')}", EXIT_NO_BALANCE)
        items = sum(len(r.get("items") or []) for r in task.get("result") or [] if isinstance(r, dict))
        return result, float(result.get("cost") or 0), items, ok

    def balance(self):
        info = http("GET", f"{self.base}/appendix/user_data", self.auth)
        money = ((info.get("tasks") or [{}])[0].get("result") or [{}])[0].get("money") or {}
        return {"balanceUsd": money.get("balance"), "totalUsd": money.get("total")}


TWITTERAPI_USD_PER_ITEM = 0.00015  # also the per-call minimum, charged on empty results
WRITE_WORDS = ("create", "delete", "send", "post_", "follow", "like", "retweet", "login", "upload")


class TwitterAPI(Provider):
    """Read-only. Writes, logins and monitoring are out of scope for a price router."""
    name, keys, site = "twitterapi", ("TWITTERAPI_IO_KEY",), "https://twitterapi.io"
    base = "https://api.twitterapi.io"

    @property
    def key(self) -> str:
        return env("TWITTERAPI_IO_KEY")

    def estimate(self, endpoint, body, fresh=True):
        return 20 * TWITTERAPI_USD_PER_ITEM if "search" in endpoint else TWITTERAPI_USD_PER_ITEM

    def call(self, endpoint, body):
        if any(w in endpoint for w in WRITE_WORDS):
            raise Stop("twitterapi.io writes and logins are not routed by getcheapapi.")
        result = http("GET", f"{self.base}/{endpoint.lstrip('/')}?{urllib.parse.urlencode(body)}", {"X-API-Key": self.key})
        rows = list_len(result) or list_len(result.get("data"))
        # twitterapi.io returns no cost: 15 credits per returned item, 15 minimum even when empty.
        return result, max(1, rows) * TWITTERAPI_USD_PER_ITEM, rows, result.get("status", "success") != "error"

    def balance(self):
        return http("GET", f"{self.base}/oapi/my/info", {"X-API-Key": self.key})


YIR_TERMINAL = {"succeeded", "failed", "cancelled"}
YIR_PATHS = {"image": "/v1/images", "video": "/v1/videos", "audio": "/v1/audio", "3d": "/v1/3d"}


class Yir(Provider):
    """Image, video, audio and 3D generation. Yir already routes each model to its cheapest channel;
    getcheapapi quotes before every job, caps it server-side with max_cost, and waits for the result.
    Text prompts only; reference uploads, batches and resumable jobs live in the yir skill/CLI."""
    name, keys, site = "yir", ("YIR_API_KEY",), "https://yir.ai"

    def __init__(self, timeout: int = 1800):
        self.base = (os.environ.get("YIR_BASE_URL") or "https://gateway.yir.ai").rstrip("/")
        self.timeout = timeout
        self._quotes: dict[str, dict] = {}

    @property
    def auth(self) -> dict:
        return {"Authorization": f"Bearer {env('YIR_API_KEY')}"}

    @staticmethod
    def request(body: dict) -> dict:
        """Capability body {model, prompt, parameters, input_type} -> Yir request body."""
        req = {"model": body["model"], "input": {"type": body.get("input_type", "text"), "prompt": body.get("prompt")},
               "parameters": body.get("parameters") or {}}
        if body.get("routing"):
            req["routing"] = body["routing"]
        return req

    def quote(self, kind: str, body: dict) -> dict:
        key = repr((kind, sorted(self.request(body).items(), key=str)))
        for attempt in range(3):  # quotes are free and idempotent: retry the gateway's transient 5xx
            if key in self._quotes:
                break
            try:
                self._quotes[key] = http("POST", f"{self.base}{YIR_PATHS[kind]}/quotes", self.auth, self.request(body), timeout=90)
            except Stop as exc:
                if not str(exc).startswith("HTTP 5") or attempt == 2:
                    raise
                time.sleep(2 * (attempt + 1))
        return self._quotes[key]

    @staticmethod
    def amount(q: dict) -> float | None:
        value = q.get("expected_amount")
        if value is None:
            value = (q.get("primary") or {}).get("amount")
        return None if value is None else float(value)

    def estimate(self, endpoint, body, fresh=True):
        q = self.quote(endpoint, body)
        if not (q.get("supply") or {}).get("available", True):
            raise Stop(f"Yir {body['model']}: no channel can take this spec now ({q.get('supply')}).")
        amount = self.amount(q)
        if amount is None:
            raise Stop(f"Yir {body['model']}: quote has no price for this spec; not running without one.")
        return amount

    def official(self, endpoint, body) -> float | None:
        o = (self.quote(endpoint, body).get("official") or {}).get("amount")
        return None if o is None else float(o)

    def prepare(self, endpoint, body):
        # Cap the job at the quote plus 10% headroom; Yir refuses with YIR_BUDGET_EXCEEDED past it.
        return {**body, "max_cost": f"{self.estimate(endpoint, body) * 1.1:.4f}"}

    def call(self, endpoint, body):
        req = {**self.request(body), "max_cost": body["max_cost"]}
        job = http("POST", f"{self.base}{YIR_PATHS[endpoint]}/generations",
                   {**self.auth, "Idempotency-Key": str(uuid.uuid4())}, req)
        start = time.time()
        while job.get("status") not in YIR_TERMINAL:
            if time.time() - start > self.timeout:
                raise Stop(f"Yir job {job.get('id')} still {job.get('status')} after {self.timeout}s; "
                           "it may still be charged. Check it later with the yir CLI: job <id>.")
            status = http("GET", f"{self.base}/v1/jobs/{job['id']}/status?wait=20", self.auth, timeout=60)
            if status.get("status") in YIR_TERMINAL:
                job = http("GET", f"{self.base}/v1/jobs/{job['id']}", self.auth)
            else:
                job = {**job, **status}
        charged = float((job.get("billing") or {}).get("total_charged_by_yir") or 0)
        files = (job.get("result") or {}).get("files") or []
        return job, charged, len(files), job.get("status") == "succeeded"

    def download(self, job: dict, out_dir: Path, stem: str) -> list[str]:
        import urllib.request
        paths = []
        files = (job.get("result") or {}).get("files") or []
        for i, f in enumerate(files):
            ext = Path(urllib.parse.urlparse(f["url"]).path).suffix or ".bin"
            path = out_dir / f"{stem}{f'-{i + 1}' if len(files) > 1 else ''}{ext}"
            out_dir.mkdir(parents=True, exist_ok=True)
            with urllib.request.urlopen(f["url"], timeout=300) as resp:  # signed URL, no key sent
                path.write_bytes(resp.read())
            paths.append(str(path))
        return paths

    def balance(self):
        raise Stop("Yir has no balance API here; see the Yir Console at https://yir.ai.")


PROVIDERS: dict[str, type[Provider]] = {p.name: p for p in (AnyAPI, GoAnyAPI, DataForSEO, TwitterAPI, Yir)}
