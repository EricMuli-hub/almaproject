"""Watcher (catches calls made straight to the node) and the Chapter Three style dataset evaluation."""
from sqlalchemy import select
from eth_account import Account
from app.db import User, LedgerEvent, Anomaly
from app.watcher import Watcher
from app import dataset
from tests.conftest import *  # noqa


def test_watcher_catches_calls_that_skip_our_api(world):
    c, h = world; core = c.core
    w = Watcher(core, start_block=core.chain.latest() + 1)
    with core.Session() as db: adm = db.execute(select(User).where(User.email == "admina@uni.test")).scalar()
    key = core.key_of(adm)
    for _ in range(7):   # a stolen admin key used directly against the node, forbidden role changes
        core.chain.send_unchecked("registerEmployer", key, Account.create().address)
    with core.Session() as db:
        seen = w.scan(db)
        assert seen >= 7
        ev = db.execute(select(LedgerEvent).where(LedgerEvent.source == "ledger")).scalars().all()
        assert len(ev) >= 7 and all(not e.success for e in ev)
        assert any(a.severity in ("high", "critical") for a in db.execute(select(Anomaly)).scalars())


def test_dataset_evaluation_runs_and_reports_both_variants():
    spec = dataset.evaluate(seed=42, hard=False); hard = dataset.evaluate(seed=42, hard=True)
    assert spec["test"] == 3000 and spec["train"] == 7000
    assert 0 <= hard["recall"] <= spec["recall"] + 1e-9 and spec["recall"] > .8
    assert set(spec["confusion"]) == {"TP", "FP", "FN", "TN"}
