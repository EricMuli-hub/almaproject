"""Ledger watcher: the Python daemon from the proposal. It reads every block from the node, picks out the
transactions sent to the registry, and scores each one with the AI monitor, whether or not the call came through
our API. That is what catches a stolen admin key used directly against the node."""
import math, threading, time
from collections import Counter
from sqlalchemy import select
from .chain import TxResult
from .db import LedgerEvent, Institution


def entropy(data: bytes) -> float:
    if not data: return 0.0
    n = len(data); return round(-sum(c / n * math.log2(c / n) for c in Counter(data).values()), 3)


class Watcher:
    def __init__(self, core, poll_s=1.0, start_block=None):
        self.core = core; self.poll = poll_s; self.next = (core.chain.latest() + 1) if start_block is None else start_block; self.stop = False

    def scan(self, db):
        ch = self.core.chain; seen = 0; last = ch.latest()
        while self.next <= last:
            for t in ch.contract_txs(self.next):
                if db.execute(select(LedgerEvent.id).where(LedgerEvent.tx_hash == t["hash"])).first(): continue   # already scored when our API sent it
                err = "" if t["ok"] else ch.replay_error(t["block"], t["hash"])
                inst = None
                try:
                    i = ch.c.functions.instOfAdmin(t["sender"]).call(); inst = i or None
                except Exception: pass
                size = int(t["args"].get("count", 1)) if t["name"] == "anchorBatch" else 1
                self.core._event(db, t["sender"], inst, t["name"], TxResult(t["ok"], err, t["gas"], t["hash"], t["block"]), size,
                                 ts=t["ts"], entropy=entropy(t["input"]), source="ledger")
                seen += 1
            self.next += 1
        db.commit(); return seen

    def run(self):
        while not self.stop:
            try:
                with self.core.Session() as db: self.scan(db)
            except Exception: pass
            time.sleep(self.poll)

    def start(self): threading.Thread(target=self.run, daemon=True).start(); return self
