"""python scripts/benchmark.py [--rpc URL --funder-key KEY] [--out docs/BENCHMARK.md]"""
import argparse, json, pathlib, sys, tempfile
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from app.core import Settings
from app.service import App
from app import bench

p = argparse.ArgumentParser(); p.add_argument("--rpc", default=""); p.add_argument("--funder-key", default=""); p.add_argument("--out", default="")
a = p.parse_args()
core = App(Settings(data_dir=tempfile.mkdtemp(), rpc_url=a.rpc, funder_key=a.funder_key))
with core.Session() as db: core.ensure_platform_admin(db, "bench@alma.local", "bench-password-1")
r = bench.full(core); r["chain"] = "json-rpc node" if a.rpc else "in-process test chain"
md = bench.markdown(r).replace("Measured on the in-process test chain.", f"Measured on: {r['chain']}.")
print(md)
if a.out:
    pathlib.Path(a.out).write_text(md + "\n"); pathlib.Path(a.out).with_suffix(".json").write_text(json.dumps(r, indent=1))
