"""AI anomaly monitor. An Isolation Forest learns what normal administrator behaviour on the ledger looks
like, a small rule engine catches hard violations (unauthorized attempts), and every ledger action is
scored the moment it happens. Training data here is synthetic until real traffic exists; the model can be
retrained from confirmed-normal events with Monitor.retrain()."""
import math, random, pathlib
from datetime import datetime, timezone, timedelta
import numpy as np
from sklearn.ensemble import IsolationForest
import joblib

UTC_OFFSET_H = 3          # East Africa Time; working hours are judged in local time
WORK_START, WORK_END = 6, 20
FEATURES = ["burst_5m", "events_1h", "events_24h", "off_hours", "fail_ratio_1h", "revoke_ratio_24h",
            "batch_size", "unauthorized_24h", "min_gap_s"]


def _hour(ts): return (datetime.fromtimestamp(ts, timezone.utc) + timedelta(hours=UTC_OFFSET_H)).hour


def featurize(hist, ev):
    """hist: earlier events of the same actor [{ts,name,success,size,error}], ev: current event."""
    t = ev["ts"]
    h24 = [h for h in hist if t - h["ts"] <= 86400] + [ev]
    h1 = [h for h in h24 if t - h["ts"] <= 3600]
    h5 = [h for h in h24 if t - h["ts"] <= 300]
    fails = sum(1 for h in h1 if not h["success"])
    revs = sum(1 for h in h24 if "revoke" in h["name"].lower())
    unauth = sum(1 for h in h24 if not h["success"] and ("NotAllowed" in h.get("error", "") or "Wrong" in h.get("error", "")))
    ts_sorted = sorted(h["ts"] for h in h24)[-10:]
    gaps = [b - a for a, b in zip(ts_sorted, ts_sorted[1:])]
    min_gap = min(gaps) if gaps else 3600
    off = 0 if WORK_START <= _hour(t) < WORK_END else 1
    v60 = sum(1 for h in h24 if t - h["ts"] <= 60)
    raw = dict(temporal_fraction=round(_hour(t) + (t % 3600) / 3600, 2), invocation_velocity=v60, payload_entropy=ev.get("entropy", 0.0),
               burst_5m=len(h5), events_1h=len(h1), events_24h=len(h24), off_hours=off,
               fail_ratio_1h=fails / max(1, len(h1)), revoke_ratio_24h=revs / max(1, len(h24)),
               batch_size=ev.get("size", 1), unauthorized_24h=unauth, min_gap_s=min_gap)
    vec = [math.log1p(raw["burst_5m"]), math.log1p(raw["events_1h"]), math.log1p(raw["events_24h"]), raw["off_hours"],
           raw["fail_ratio_1h"], raw["revoke_ratio_24h"], math.log1p(raw["batch_size"]), math.log1p(raw["unauthorized_24h"]),
           math.log1p(min_gap)]
    return raw, vec


# ---------- synthetic traffic ----------
def simulate_normal(days=60, seed=1, start=1_700_000_000):
    rnd = random.Random(seed); out = []
    for d in range(days):
        if d % 7 in (5, 6) and rnd.random() < .8: continue
        base = start + d * 86400
        day0 = base - (base % 86400) - UTC_OFFSET_H * 3600
        n = max(1, int(rnd.gauss(14, 6)))
        times = []
        for _ in range(n):
            t0 = day0 + int(rnd.uniform(8, 17.5) * 3600)
            times.append(t0)
            if rnd.random() < .2:                      # people often work in short runs (registering a class, issuing a few records)
                for k in range(rnd.randint(2, 11)): times.append(t0 + (k + 1) * rnd.randint(8, 40))
        times.sort()
        for t in times:
            roll = rnd.random()
            if roll < .04: name, size = "anchorBatch", int(min(4000, rnd.lognormvariate(5.2, 1.0)))
            elif roll < .07: name, size = "revokeCredential", 1
            elif roll < .10: name, size = "registerStudent", 1
            else: name, size = "issueCredential", 1
            ok = rnd.random() > .02
            out.append(dict(ts=t, name=name, success=ok, size=size, error="" if ok else "AlreadyExists"))
    return out


def rows_from(events):
    X, hist = [], []
    for ev in events:
        raw, vec = featurize(hist, ev); X.append(vec); hist.append(ev)
        hist = [h for h in hist if ev["ts"] - h["ts"] <= 86400]
    return np.array(X)


def attack(kind, seed=3, start=1_700_000_000 + 80 * 86400):
    rnd = random.Random(seed)
    t0 = start - (start % 86400) - UTC_OFFSET_H * 3600
    ev = []
    if kind == "burst_offhours":
        t = t0 + int(2.5 * 3600)
        for i in range(60): ev.append(dict(ts=t + i * 2, name="issueCredential", success=True, size=1, error=""))
    elif kind == "unauthorized_attempts":
        t = t0 + 11 * 3600
        for i in range(8): ev.append(dict(ts=t + i * 60, name="issueCredential", success=False, size=1, error="NotAllowed(needed=UniversityAdmin,actual=Student)"))
    elif kind == "revocation_storm":
        t = t0 + 14 * 3600
        for i in range(40): ev.append(dict(ts=t + i * 20, name="revokeCredential", success=True, size=1, error=""))
    elif kind == "mass_batch_offhours":
        ev.append(dict(ts=t0 + int(2 * 3600), name="anchorBatch", success=True, size=60000, error=""))
    return ev


class Monitor:
    def __init__(self, data_dir):
        self.path = pathlib.Path(data_dir) / "ai_model.joblib"
        if self.path.exists():
            self.model, self.ref, self.mu, self.sd = joblib.load(self.path)
        else:
            self.train(rows_from(simulate_normal()))

    def train(self, X):
        self.model = IsolationForest(n_estimators=250, contamination="auto", random_state=7).fit(X)
        self.ref = np.sort(self.model.score_samples(X))        # normal-score distribution for calibration
        self.mu, self.sd = X.mean(axis=0), X.std(axis=0) + 1e-6
        joblib.dump((self.model, self.ref, self.mu, self.sd), self.path)

    def retrain(self, extra_normal_events=None):
        ev = simulate_normal() + (extra_normal_events or [])
        self.train(rows_from(sorted(ev, key=lambda e: e["ts"])))

    def _model_risk(self, vec):
        s = self.model.score_samples(np.array([vec]))[0]
        pct = 1 - np.searchsorted(self.ref, s) / len(self.ref)     # share of normal events that look more normal
        # pct is small when the event is rarer than normal traffic
        rarity = 1 - pct
        iso = float(min(1.0, max(0.0, (rarity - 0.985) / 0.015))) * 0.95
        z = (np.array(vec) - self.mu) / self.sd
        idx = [0, 1, 2, 6, 7] + ([5] if vec[2] >= math.log1p(8) else [])
        zmax = float(max(z[i] for i in idx))
        zr = float(min(1.0, max(0.0, (zmax - 5.0) / 5.0))) * 0.9
        if vec[3] == 1: zr = min(0.95, zr * 1.3)
        return max(iso, zr)

    def assess(self, hist, ev):
        raw, vec = featurize(hist, ev); reasons = []
        risk = self._model_risk(vec)
        if risk > 0:
            if raw["burst_5m"] >= 10: reasons.append(f'{raw["burst_5m"]} actions in 5 minutes (normal is 1 to 3)')
            if raw["off_hours"]: reasons.append("activity outside working hours")
            if raw["batch_size"] >= 6000: reasons.append(f'batch of {raw["batch_size"]} records is far above past batches')
            if raw["revoke_ratio_24h"] >= .4 and raw["events_24h"] >= 10: reasons.append("unusually many revocations")
        rule = 0.0
        if raw["unauthorized_24h"] >= 6: rule = .92; reasons.append(f'{raw["unauthorized_24h"]} unauthorized attempts in 24 hours')
        elif raw["unauthorized_24h"] >= 3: rule = .72; reasons.append(f'{raw["unauthorized_24h"]} unauthorized attempts in 24 hours')
        elif raw["unauthorized_24h"] >= 1 and ev["name"].startswith(("register", "setInstitution")) and not ev["success"]:
            rule = .5; reasons.append("attempt to change roles or status without permission")
        if raw["burst_5m"] >= 40: rule = max(rule, .8); reasons.append("issuing rate beyond any normal pace")
        elif raw["burst_5m"] >= 20: rule = max(rule, .55); reasons.append(f'{raw["burst_5m"]} actions in 5 minutes, well above a person working by hand')
        if raw["off_hours"] and raw["burst_5m"] >= 12: rule = max(rule, .72); reasons.append("fast activity outside working hours")
        if ev["name"] in ("anchorBatch",) and ev["size"] >= 20000: rule = max(rule, .75)
        score = max(risk, rule)
        sev = "critical" if score >= .9 else "high" if score >= .7 else "medium" if score >= .5 else "none"
        return dict(score=round(score, 3), severity=sev, reasons=sorted(set(reasons)) or (["unusual pattern of ledger activity"] if sev != "none" else []), features=raw)


def evaluate(seed=11):
    """Held-out check on synthetic traffic: false alarms on unseen normal days and detection of 4 attack types."""
    m = Monitor.__new__(Monitor)
    import tempfile
    m.path = pathlib.Path(tempfile.mkdtemp()) / "m.joblib"
    m.train(rows_from(simulate_normal(seed=seed)))
    test = simulate_normal(days=40, seed=seed + 100, start=1_700_000_000 + 90 * 86400)
    hist, flagged, total = [], 0, 0
    for ev in test:
        a = m.assess(hist, ev); total += 1; flagged += a["severity"] != "none"
        hist.append(ev); hist = [h for h in hist if ev["ts"] - h["ts"] <= 86400]
    res = {"normal_events": total, "false_alarms": flagged, "false_alarm_rate": round(flagged / total, 4), "attacks": {}}
    for k in ("burst_offhours", "unauthorized_attempts", "revocation_storm", "mass_batch_offhours"):
        hist, worst, first = [], "none", None
        for i, ev in enumerate(attack(k)):
            a = m.assess(hist, ev); hist.append(ev)
            if a["severity"] != "none" and first is None: first = i + 1
            if ["none", "medium", "high", "critical"].index(a["severity"]) > ["none", "medium", "high", "critical"].index(worst): worst = a["severity"]
        res["attacks"][k] = {"detected": worst != "none", "worst": worst, "detected_at_event": first, "events": len(attack(k))}
    res["detected"] = sum(v["detected"] for v in res["attacks"].values()); res["scenarios"] = 4
    return res
