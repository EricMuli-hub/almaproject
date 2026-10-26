"""Measurements for objective 5: latency, scalability and transaction cost of the hybrid design against a
conventional centralized registry. Gas is exact for this contract; fiat cost needs a gas price and a coin price,
which are inputs you set, not facts this code knows."""
import json, secrets, statistics, time
from concurrent.futures import ThreadPoolExecutor
from sqlalchemy import select
from .core import merkle_levels, merkle_proof, verify_proof, sha
from .db import User, Credential

EXAMPLE_GAS_PRICES_GWEI = {"mainnet-like (assumed)": 20.0, "layer-2-like (assumed)": 0.05}
EXAMPLE_COIN_USD = 3000.0   # placeholder input; replace with the current price


def _setup(core, tag=None):
    tag = tag or secrets.token_hex(3)
    with core.Session() as db:
        owner = db.execute(select(User).where(User.role == "platform_admin")).scalar()
        inst = core.create_institution(db, owner, f"Bench Uni {tag}", f"bench{tag}@uni.test", "password-123")
        adm = db.execute(select(User).where(User.email == f"bench{tag}@uni.test")).scalar()
        st = core.add_student(db, adm, f"stu{tag}@mail.test", "Bench Student")
        return adm.email, st.email


def _admin(db, email): return db.execute(select(User).where(User.email == email)).scalar()


def pct(xs, p): xs = sorted(xs); return xs[min(len(xs) - 1, int(len(xs) * p))]


def cost(gas, gwei, coin_usd=EXAMPLE_COIN_USD): return gas * gwei * 1e-9 * coin_usd


def quick(core, n_verify=60):
    adm_email, stu = _setup(core)
    rec = lambda i: {"student_no": f"S{i}", "award": "BSc", "year": 2025, "n": i}
    with core.Session() as db:
        adm = _admin(db, adm_email)
        single = core.issue_single(db, adm, stu, rec(0), "Degree")
        t = time.perf_counter()
        b = core.issue_batch(db, adm, [{"holder_email": stu, "record": rec(i + 1), "label": "Transcript"} for i in range(1000)])
        batch_s = time.perf_counter() - t
        a = b["anchors"][0]
        ids = b["credential_ids"]
        # verification latency: hybrid (database + merkle proof + chain read) against a plain database lookup
        hy, ce, hc = [], [], []
        ttl = core.s.read_cache_ttl; core.s.read_cache_ttl = 0; core._rc.clear()
        for cid in ids[:n_verify]:
            t = time.perf_counter(); core.verify(db, cid); hy.append((time.perf_counter() - t) * 1000)
            t = time.perf_counter(); c = db.get(Credential, cid); _ = (c.status == "issued"); ce.append((time.perf_counter() - t) * 1000)
        core.s.read_cache_ttl = 5.0; core._rc.clear()
        for cid in ids[:n_verify]: core.verify(db, cid)                  # warm the status cache
        for cid in ids[:n_verify]:
            t = time.perf_counter(); core.verify(db, cid); hc.append((time.perf_counter() - t) * 1000)
        core.s.read_cache_ttl = ttl; core._rc.clear()
    merk = {}
    for n in (1_000, 10_000, 100_000):
        leaves = [sha(i.to_bytes(8, "big")) for i in range(n)]
        t = time.perf_counter(); lv = merkle_levels(leaves); bs = time.perf_counter() - t
        pr = merkle_proof(lv, n // 2); t = time.perf_counter(); ok = verify_proof(leaves[n // 2], pr, lv[-1][0]); vs = time.perf_counter() - t
        merk[str(n)] = dict(build_s=round(bs, 3), proof_hashes=len(pr), proof_bytes=len(pr) * 32, verify_ms=round(vs * 1000, 4), ok=ok)
    return dict(
        gas=dict(single_issue=single["gas"], batch_1000_total=a["gas"], batch_1000_per_record=round(a["gas"] / 1000, 1)),
        batch_issue_1000_wall_s=round(batch_s, 2),
        merkle=merk,
        verify=dict(samples=n_verify, hybrid_p50_ms=round(statistics.median(hy), 3), hybrid_p95_ms=round(pct(hy, .95), 3),
                    cached_p50_ms=round(statistics.median(hc), 3), cached_p95_ms=round(pct(hc, .95), 3),
                    central_p50_ms=round(statistics.median(ce), 4), central_p95_ms=round(pct(ce, .95), 4)))


def full(core):
    r = quick(core)
    # throughput of verification with 8 concurrent clients
    adm_email, stu = _setup(core)
    with core.Session() as db:
        adm = _admin(db, adm_email)
        ids = core.issue_batch(db, adm, [{"holder_email": stu, "record": {"n": i}} for i in range(500)])["credential_ids"]
    def one(cid):
        with core.Session() as db: return core.verify(db, cid)["valid"]
    t = time.perf_counter()
    with ThreadPoolExecutor(8) as ex: ok = list(ex.map(one, ids * 4))
    r["verify_throughput_per_s_8_clients"] = round(len(ok) / (time.perf_counter() - t), 1); r["all_valid"] = all(ok)
    # transaction cost model per 10,000 records
    gas = r["gas"]; rows = []
    for name, gwei in EXAMPLE_GAS_PRICES_GWEI.items():
        rows.append(dict(network=name, gas_price_gwei=gwei, one_tx_each_usd=round(cost(gas["single_issue"], gwei) * 10_000, 2),
                         one_batch_usd=round(cost(gas["batch_1000_total"], gwei) * 10, 2)))
    r["gas_table"] = gas_table()
    r["concurrency_nocache"] = concurrency(core, ttl=0.0, rounds=2)
    r["concurrency_cache5s"] = concurrency(core, ttl=5.0, rounds=2)
    r["cost_per_10000_records"] = dict(assumed_coin_usd=EXAMPLE_COIN_USD, rows=rows, note="gas figures are measured; prices are assumptions")
    return r


def markdown(r):
    g = r["gas"]; v = r["verify"]
    L = ["# Benchmark results (objective 5)", "",
         "Measured on the in-process test chain. Chain latency here is near zero, so the latency numbers show the cost of the software around the chain, "
         "not network or block time. Point CHAIN_RPC at a real node and run `python scripts/benchmark.py` to measure those.", "",
         "## Transaction cost (gas, exact for this contract)", "", "| | gas |", "|---|---|",
         f"| issue one record on its own | {g['single_issue']:,} |", f"| anchor a batch of 1,000 | {g['batch_1000_total']:,} |",
         f"| per record in that batch | {g['batch_1000_per_record']:,} |", ""]
    if "cost_per_10000_records" in r:
        c = r["cost_per_10000_records"]
        L += [f"## Cost for 10,000 records (assumed coin price ${c['assumed_coin_usd']:,.0f}; gas prices are assumptions)", "", "| network | gas price (gwei) | one transaction each | batches of 1,000 |", "|---|---|---|---|"]
        L += [f"| {x['network']} | {x['gas_price_gwei']} | ${x['one_tx_each_usd']:,} | ${x['one_batch_usd']:,} |" for x in c["rows"]] + [""]
    if "gas_table" in r:
        L += ["## Gas by contract method (Table 3.3 layout)", "", "Standard = compiled without the optimizer, optimized = optimizer on (200 runs). Measured, not estimated.", "",
              "| method | gas (standard) | gas (optimized) |", "|---|---|---|"]
        L += [f"| {k} | {v['standard']:,} | {v['optimized']:,} |" for k, v in r["gas_table"].items() if not k.endswith("_ms")]
        L += [f"| verifyCredential (view) latency | {r['gas_table']['verifyCredential_call_ms']['standard']} ms | {r['gas_table']['verifyCredential_call_ms']['optimized']} ms |", ""]
    for key, title in (("concurrency_nocache", "every request reads the chain"), ("concurrency_cache5s", "chain reads cached for 5 s")):
        if key in r:
            c = r[key]
            L += [f"## Concurrent verification, {title}", "", "A burst of N simultaneous GET /verify calls against a running server, 2 rounds per level.", "",
                  "| concurrent | ok | min ms | median ms | mean ms | p95 ms | max ms | requests/s |", "|---|---|---|---|---|---|---|---|"]
            L += [f"| {x['concurrent']} | {x['ok']}/{x['total']} | {x['min_ms']} | {x['median_ms']} | {x['mean_ms']} | {x['p95_ms']} | {x['max_ms']} | {x['tps']} |" for x in c["rows"]]
            L += ["", f"Process memory: {c['rss_start_mb']} MB before, {c['rss_end_mb']} MB after.", ""]
    L += ["## Verification latency", "", "| | median (ms) | 95th percentile (ms) |", "|---|---|---|",
          f"| hybrid, every check reads the chain | {v['hybrid_p50_ms']} | {v['hybrid_p95_ms']} |",
          f"| hybrid with the 5 second chain-status cache | {v['cached_p50_ms']} | {v['cached_p95_ms']} |",
          f"| centralized lookup only (no integrity proof) | {v['central_p50_ms']} | {v['central_p95_ms']} |", ""]
    if "verify_throughput_per_s_8_clients" in r: L += [f"Verification throughput with 8 concurrent clients: {r['verify_throughput_per_s_8_clients']} per second.", ""]
    L += ["## Scalability of the Merkle tree", "", "| records | build (s) | proof hashes | proof bytes | verify (ms) |", "|---|---|---|---|---|"]
    L += [f"| {int(k):,} | {m['build_s']} | {m['proof_hashes']} | {m['proof_bytes']} | {m['verify_ms']} |" for k, m in r["merkle"].items()]
    L += ["", f"Issuing 1,000 records in one batch took {r['batch_issue_1000_wall_s']} s end to end (encryption, storage, anchoring)."]
    return "\n".join(L)


# ---------- gas profile in the layout of Table 3.3 ----------
def gas_profile(artifact):
    """Fresh chain, one measurement per method. Uses the contract method names from the report."""
    from eth_account import Account
    from .chain import Chain
    ch = Chain(artifact=artifact); p = ch.platform.key
    adm, stu, emp = Account.create(), Account.create(), Account.create()
    for a in (adm, stu, emp): ch.fund(a.address)
    out = {"constructor": ch.deploy_gas}
    ch.tx("registerInstitution", p, adm.address, "Gas Uni")
    out["grantRole (employer)"] = ch.tx("grantRole", p, emp.address, 4).gas
    out["registerStudent"] = ch.tx("registerStudent", adm.key, stu.address).gas
    out["mintCredential"] = ch.tx("mintCredential", adm.key, b"\x11" * 32, stu.address, "QmGasMeasurement1234567890123456789012345678901").gas
    out["revokeCredential"] = ch.tx("revokeCredential", adm.key, b"\x11" * 32).gas
    out["anchorBatch (any size)"] = ch.tx("anchorBatch", adm.key, b"\x22" * 32, 1000, "QmManifest").gas
    t = time.perf_counter()
    for _ in range(200): ch.c.functions.verifyCredential(b"\x11" * 32).call()
    out["verifyCredential"] = 0; out["verifyCredential_call_ms"] = round((time.perf_counter() - t) / 200 * 1000, 3)
    return out


def gas_table():
    a = gas_profile("AlmaRegistry.noopt.json"); b = gas_profile("AlmaRegistry.json")
    return {k: dict(standard=a[k], optimized=b[k]) for k in a}


# ---------- latency and throughput at 10, 50, 100, 500, 1000 simultaneous calls ----------
def concurrency(core, levels=(10, 50, 100, 500, 1000), ttl=0.0, rounds=3):
    import asyncio, os, threading, httpx, psutil, uvicorn
    from fastapi import FastAPI
    from .api import create_app
    adm_email, stu = _setup(core)
    with core.Session() as db:
        adm = _admin(db, adm_email)
        ids = core.issue_batch(db, adm, [{"holder_email": stu, "record": {"n": i}} for i in range(300)])["credential_ids"]
    core.s.read_cache_ttl = ttl; core._rc.clear()
    api = FastAPI()
    @api.get("/verify/{cid}")
    def v(cid: str):
        with core.Session() as db: return core.verify(db, cid)
    port = 18000 + (os.getpid() % 1000)
    srv = uvicorn.Server(uvicorn.Config(api, host="127.0.0.1", port=port, log_level="error", limit_concurrency=None, backlog=4096))
    th = threading.Thread(target=srv.run, daemon=True); th.start()
    for _ in range(100):
        if srv.started: break
        time.sleep(.1)
    proc = psutil.Process(); rss0 = proc.memory_info().rss / 1e6
    async def burst(n):
        lat, ok = [], 0
        async with httpx.AsyncClient(base_url=f"http://127.0.0.1:{port}", limits=httpx.Limits(max_connections=n, max_keepalive_connections=n), timeout=120) as c:
            async def one(i):
                t = time.perf_counter(); r = await c.get(f"/verify/{ids[i % len(ids)]}"); lat.append((time.perf_counter() - t) * 1000); return r.status_code == 200 and r.json()["valid"]
            t0 = time.perf_counter(); res = await asyncio.gather(*[one(i) for i in range(n)]); wall = time.perf_counter() - t0
        return lat, sum(res), wall
    rows = []
    for n in levels:
        allat, okc, tot, walls = [], 0, 0, []
        for _ in range(rounds):
            lat, ok, wall = asyncio.run(burst(n)); allat += lat; okc += ok; tot += n; walls.append(wall)
        rows.append(dict(concurrent=n, ok=okc, total=tot, min_ms=round(min(allat), 1), max_ms=round(max(allat), 1), mean_ms=round(statistics.mean(allat), 1),
                         median_ms=round(statistics.median(allat), 1), p95_ms=round(pct(allat, .95), 1), tps=round(n / statistics.mean(walls), 1)))
    rss1 = proc.memory_info().rss / 1e6
    srv.should_exit = True
    return dict(read_cache_ttl_s=ttl, rows=rows, rss_start_mb=round(rss0, 1), rss_end_mb=round(rss1, 1))
