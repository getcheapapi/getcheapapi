"""getcheapapi: call paid data and media APIs through the cheapest upstream, behind budget guards.

Every paid run: price all routes, pick the cheapest one you have a key for, re-price it on fresh prices,
refuse past --max-usd, stop on 402 or the first failure, save the full response, and append one ledger
line per call. AnyAPI calls are pinned to sources within --max-ratio of the cheapest, with failover off.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

from getcheapapi import lanes as L
from getcheapapi import router
from getcheapapi.core import Stop, env, home, ledger_path, load_env, now, record, write_json
from getcheapapi.providers import DATA_DIR, PROVIDERS, AnyAPI, GoAnyAPI, Provider


def read_input(raw: str):
    text = Path(raw[1:]).read_text(encoding="utf-8") if raw.startswith("@") else raw
    try:
        return json.loads(text)
    except ValueError as exc:
        raise Stop(f"--input is not valid JSON: {exc}") from None


def client_for(name: str, args) -> Provider:
    return AnyAPI(args.max_ratio) if name == "anyapi" else PROVIDERS[name]()


def execute(client: Provider, endpoint: str, bodies: list[dict], args, label: str, extra: dict | None = None) -> int:
    """Prepare on fresh prices, estimate, enforce --max-usd, call one by one, record and save."""
    bodies = [client.prepare(endpoint, b) for b in bodies]
    estimate = sum(client.estimate(endpoint, b) for b in bodies)
    print(json.dumps({"route": label, "calls": len(bodies), "estimateUsd": round(estimate, 5), "maxUsd": args.max_usd}))
    if estimate > args.max_usd:
        raise Stop(f"estimate ${estimate:.4f} exceeds --max-usd {args.max_usd}; tell the user the count and total, "
                   "then rerun with a higher --max-usd once they agree.")

    stamp = f"{datetime.now():%Y%m%d-%H%M%S}"
    out = Path(args.output) if args.output else home() / "results" / client.name / f"{endpoint.replace('/', '_')}-{stamp}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    responses, files, spent, code = [], [], 0.0, 0
    for body in bodies:
        row = {"at": now(), "provider": client.name, "endpoint": endpoint, "project": args.project,
               "input": {k: v for k, v in body.items() if k not in ("source", "allowFallbacks")}, **(extra or {})}
        try:
            result, cost, rows, ok = client.call(endpoint, body)
        except Stop as exc:
            spent += exc.cost
            record({**row, "costUsd": round(exc.cost, 6), "error": str(exc)[:300]})
            print(str(exc), file=sys.stderr)
            code = exc.code
            break
        spent += cost
        responses.append(result)
        source = (result.get("source") or {}).get("id") if isinstance(result, dict) else None
        record({**row, "costUsd": round(cost, 6), "rows": rows, **({"source": source} if source else {}),
                **({} if ok else {"error": "call failed"})})
        if isinstance(result, dict) and result.get("nextAction"):  # async AnyAPI: poll, never resubmit
            print(json.dumps({"requestId": result.get("requestId"), "nextAction": result["nextAction"]}))
        if client.name == "yir" and ok:
            files += client.download(result, out.parent, out.stem)
        if not ok:
            print(f"call failed: {json.dumps(result, ensure_ascii=False)[:600]}", file=sys.stderr)
            code = 1
            break
        if spent > args.max_usd:
            print(f"spent ${spent:.4f} passed --max-usd {args.max_usd}; stopping", file=sys.stderr)
            code = 1
            break

    if responses:
        out.write_text(json.dumps(responses if len(bodies) > 1 else responses[0], ensure_ascii=False, indent=2),
                       encoding="utf-8")
    print(json.dumps({"saved": str(out) if responses else None, **({"files": files} if files else {}),
                      "done": len(responses), "of": len(bodies), "spentUsd": round(spent, 6)}))
    return code


def as_inputs(parsed) -> list[dict]:
    inputs = parsed if isinstance(parsed, list) else [parsed]
    if not inputs or not all(isinstance(i, dict) for i in inputs):
        raise Stop("--input must be a JSON object or a list of objects")
    return inputs


def cmd_caps(args) -> int:
    keys = {name: cls.configured() for name, cls in PROVIDERS.items()}
    print("providers: " + "  ".join(f"{n}{'' if ok else ' (no key)'}" for n, ok in keys.items()))
    for name, cap in router.load_catalog().items():
        providers = sorted({r["provider"] for r in cap["routes"]})
        print(f"  {name:18} {cap['description']}  [{', '.join(providers)}]")
        if args.verbose:
            print(f"  {'':18} input: {json.dumps(cap['input'], ensure_ascii=False)}")
            print(f"  {'':18} e.g.   {json.dumps(cap['example'], ensure_ascii=False)}")
    return 0


def cmd_quote(args) -> int:
    cap = router.capability(args.capability)
    inputs = as_inputs(read_input(args.input))
    options = router.plan(cap, inputs, {"anyapi": AnyAPI(args.max_ratio)}, args.via)
    print(f"{args.capability}: {len(inputs)} input(s), prices per run (no money spent)")
    print(router.table(options))
    runnable = [o for o in options if o.status == "ok"]
    if runnable:
        best = runnable[0]
        cheaper = [o for o in options if o.status == "no key" and o.usd is not None and o.usd < (best.usd or 0) - 1e-12]
        print(f"would run: {best.label} ${best.usd:.5f}")
        for o in cheaper:
            print(f"  a key for {o.provider} ({PROVIDERS[o.provider].site}) would save ${best.usd - o.usd:.5f} on this run")
    return 0


def cmd_run(args) -> int:
    cap = router.capability(args.capability)
    inputs = as_inputs(read_input(args.input))
    if cap.get("media") and not inputs[0].get("model"):
        raise Stop("media runs need a model: compare with `getcheapapi quote` first, then pass the one whose "
                   "quality fits as \"model\" in --input")
    clients: dict[str, Provider] = {"anyapi": AnyAPI(args.max_ratio)}
    options = router.plan(cap, inputs, clients, args.via)
    print(router.table(options), file=sys.stderr)
    best = router.choose(options)
    return execute(clients[best.provider], best.endpoint, best.bodies, args, best.label,
                   {"capability": args.capability})


def cmd_call(args) -> int:
    client = client_for(args.provider, args)
    parsed = read_input(args.input)
    return execute(client, args.endpoint, as_inputs(parsed), args, f"{args.provider} {args.endpoint}")


def cmd_prices(args) -> int:
    if args.action == "show":
        for path in sorted((home() / "prices").glob("*.json")):
            data = json.loads(path.read_text(encoding="utf-8"))
            ats = [v["at"] for v in data.values() if isinstance(v, dict) and "at" in v] or [data.get("at")]
            print(f"{path.name:16} {len(data)} entries, oldest {min(a for a in ats if a)}")
        return 0
    refreshed = {}
    credits = GoAnyAPI.refresh_prices()
    refreshed["goanyapi"] = len(credits)
    skus = sorted({r["endpoint"] for c in router.load_catalog().values() for r in c["routes"] if r["provider"] == "anyapi"})
    cheapest = {}
    if AnyAPI.configured():
        key = env("ANYAPI_API_KEY")
        for sku in skus:
            lanes = L.fetch_lanes(sku, key)
            cheapest[sku] = min((L.lane_price(l, {}) for l in lanes), default=None)
        refreshed["anyapi"] = len(skus)
    else:
        print("anyapi: no key, kept the bundled snapshot", file=sys.stderr)
    print(json.dumps({"refreshed": refreshed, "at": now(), "cache": str(home() / "prices")}))
    if args.write_snapshot:  # maintainers: update the bundled snapshot that keyless comparisons read
        path = DATA_DIR / "prices.json"
        snap = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        snap["_at"] = now()[:10]
        if cheapest:
            snap["anyapi"] = {k: v for k, v in cheapest.items() if v is not None}
        snap["goanyapi"] = {k: round(v * 0.001, 6) for k, v in sorted(credits.items())}
        write_json(path, snap)
        print(f"snapshot written: {path}")
    return 0


def cmd_spend(args) -> int:
    since = datetime.now(timezone.utc) - timedelta(days=args.days)
    totals = defaultdict(lambda: [0, 0.0, 0])
    path = ledger_path()
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            r = json.loads(line)
            if datetime.fromisoformat(r["at"]) < since:
                continue
            t = totals[(r["provider"], r["endpoint"], r.get("project") or "")]
            t[0] += 1
            t[1] += r.get("costUsd") or 0
            t[2] += bool(r.get("error"))
    for (provider, endpoint, project), (n, usd, failed) in sorted(totals.items(), key=lambda x: -x[1][1]):
        print(f"{provider:10} {endpoint:44} {project:16} calls={n:<5} failed={failed:<4} ${usd:.4f}")
    print(f"total ${sum(t[1] for t in totals.values()):.4f} over {args.days} days (calls made through getcheapapi only)")
    return 0


def cmd_balance(args) -> int:
    print(json.dumps(PROVIDERS[args.provider]().balance()))
    return 0


def cmd_describe(args) -> int:
    if args.provider == "anyapi":
        client = AnyAPI()
        from getcheapapi.core import http
        info = http("GET", f"{AnyAPI.base}/apis/{args.endpoint}", {"X-API-Key": client.key})
        print(json.dumps({k: info.get(k) for k in ("id", "description", "inputSchema")}, ensure_ascii=False, indent=2))
        print(L.price_table(args.endpoint, {}, info.get("lanes") or []))
        seen = L.load_baseline().get(args.endpoint)
        print(f"baseline: ${seen['usd']} since {seen['at']}" if seen else "baseline: none yet (set on first run)")
    elif args.provider == "goanyapi":
        from getcheapapi.core import http
        apis = http("GET", f"{GoAnyAPI.base}/mcp/catalog", {})["data"]["apis"]
        found = [a for a in apis if args.endpoint in (a["id"], a["path"].rsplit("/", 1)[-1])]
        print(json.dumps(found or {"error": f"{args.endpoint} not in catalog"}, ensure_ascii=False, indent=2))
    else:
        print(f"See {PROVIDERS[args.provider].site} docs for this endpoint.")
    return 0


def cmd_accept(args) -> int:
    old, new = L.accept_price(args.sku, L.fetch_lanes(args.sku, env("ANYAPI_API_KEY")))
    print(json.dumps({"sku": args.sku, "oldUsd": old, "newUsd": new, "baseline": str(L.baseline_path())}))
    return 0


def add_spend_flags(p):
    p.add_argument("--input", required=True, help="JSON object or list of objects, or @file.json")
    p.add_argument("--max-usd", type=float, default=0.1, help="refuse when the estimate, or stop when spend, passes this")
    p.add_argument("--max-ratio", type=float, default=L.DEFAULT_MAX_RATIO,
                   help="anyapi: only sources priced within this multiple of the cheapest may serve")
    p.add_argument("--project", default=Path.cwd().name, help="tag for the ledger (default: current folder)")
    p.add_argument("-o", "--output")


def main() -> None:
    parser = argparse.ArgumentParser(prog="getcheapapi", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("caps", help="list capabilities and which providers you have keys for")
    c.add_argument("-v", "--verbose", action="store_true", help="show input fields and an example")
    q = sub.add_parser("quote", help="price every route for an input; spends nothing")
    q.add_argument("capability")
    q.add_argument("--input", required=True)
    q.add_argument("--via", choices=PROVIDERS, help="only this provider")
    q.add_argument("--max-ratio", type=float, default=L.DEFAULT_MAX_RATIO)
    r = sub.add_parser("run", help="run a capability through its cheapest route you have a key for")
    r.add_argument("capability")
    r.add_argument("--via", choices=PROVIDERS, help="force this provider")
    add_spend_flags(r)
    k = sub.add_parser("call", help="call one provider endpoint directly, with the same guards")
    k.add_argument("provider", choices=PROVIDERS)
    k.add_argument("endpoint", help="anyapi SKU, goanyapi id, dataforseo path after /v3/, twitterapi path, yir image|video|audio")
    add_spend_flags(k)
    p = sub.add_parser("prices", help="refresh or show the local price cache")
    p.add_argument("action", choices=["refresh", "show"])
    p.add_argument("--write-snapshot", action="store_true", help="maintainers: update the bundled snapshot")
    s = sub.add_parser("spend", help="sum the local ledger")
    s.add_argument("--days", type=int, default=7)
    b = sub.add_parser("balance")
    b.add_argument("provider", choices=PROVIDERS)
    d = sub.add_parser("describe", help="schema and source prices of one endpoint (anyapi, goanyapi)")
    d.add_argument("provider", choices=PROVIDERS)
    d.add_argument("endpoint")
    a = sub.add_parser("accept-price", help="anyapi: accept today's cheapest price as the baseline, after the user agrees")
    a.add_argument("sku")
    args = parser.parse_args()

    load_env()
    handlers = {"caps": cmd_caps, "quote": cmd_quote, "run": cmd_run, "call": cmd_call, "prices": cmd_prices,
                "spend": cmd_spend, "balance": cmd_balance, "describe": cmd_describe, "accept-price": cmd_accept}
    try:
        sys.exit(handlers[args.cmd](args))
    except Stop as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(exc.code)


if __name__ == "__main__":
    main()
