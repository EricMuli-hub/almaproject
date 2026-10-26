"""Synthetic ledger log that follows Chapter Three of the proposal:
N = 10,000 transactions = 9,500 normal + 250 insider abuse + 250 external script exploits,
split 70% train / 30% test, scored with an Isolation Forest on the features the proposal lists
(temporal_fraction, invocation_velocity, payload_entropy).

Everything here is synthetic. 'spec' follows the stratum definitions literally, which makes the strata easy to
separate. 'hard' blurs the boundaries (late-evening insiders, slow scripts, similar payloads) so the numbers
are not flattering. Report both and say which is which."""
import numpy as np
from sklearn.ensemble import IsolationForest
from sklearn.metrics import confusion_matrix

FEATURES = ["temporal_fraction", "invocation_velocity", "payload_entropy"]


def generate(seed=42, hard=False, n_normal=9500, n_insider=250, n_script=250):
    r = np.random.default_rng(seed)
    # stratum 1: normal office work, 08:00 to 17:00, fewer than 10 write calls a minute
    t1 = r.uniform(8, 17, n_normal)
    v1 = np.clip(r.poisson(2.2, n_normal) + 1, 1, 9)
    e1 = np.clip(r.normal(5.2, 0.35, n_normal), 3.5, 6.5)
    # stratum 2: authorized key doing mass updates or role changes outside business hours
    if not hard:
        off = r.uniform(0, 1, n_insider) < .5
        t2 = np.where(off, r.uniform(0, 6, n_insider), r.uniform(19, 24, n_insider))
        v2 = r.uniform(15, 80, n_insider); e2 = np.clip(r.normal(6.3, 0.5, n_insider), 4.5, 7.8)
    else:
        edge = r.uniform(0, 1, n_insider) < .35               # just outside office hours
        t2 = np.where(edge, np.where(r.uniform(0, 1, n_insider) < .5, r.uniform(6, 8, n_insider), r.uniform(17, 19, n_insider)),
                      np.where(r.uniform(0, 1, n_insider) < .5, r.uniform(0, 6, n_insider), r.uniform(19, 24, n_insider)))
        v2 = r.uniform(6, 30, n_insider); e2 = np.clip(r.normal(5.6, 0.5, n_insider), 4.0, 7.5)
        stealth = r.uniform(0, 1, n_insider) < .25            # insider who works inside office hours at a human pace
        t2 = np.where(stealth, r.uniform(8, 17, n_insider), t2); v2 = np.where(stealth, r.uniform(4, 12, n_insider), v2)
        e2 = np.where(stealth, np.clip(r.normal(5.4, 0.4, n_insider), 4, 7), e2)
    # stratum 3: scripted lookups from an external node: very fast, repetitive payloads
    if not hard:
        t3 = r.uniform(0, 24, n_script); v3 = r.uniform(60, 400, n_script); e3 = np.clip(r.normal(3.6, 0.4, n_script), 2.5, 4.8)
    else:
        t3 = r.uniform(0, 24, n_script); v3 = r.uniform(9, 90, n_script); e3 = np.clip(r.normal(4.6, 0.5, n_script), 3.0, 5.8)
        slow = r.uniform(0, 1, n_script) < .25               # patient scraper that stays near the normal rate
        t3 = np.where(slow, r.uniform(8, 17, n_script), t3); v3 = np.where(slow, r.uniform(4, 14, n_script), v3)
        e3 = np.where(slow, np.clip(r.normal(5.0, 0.4, n_script), 3.5, 6.5), e3)
    X = np.vstack([np.c_[t1, v1, e1], np.c_[t2, v2, e2], np.c_[t3, v3, e3]])
    y = np.r_[np.zeros(n_normal), np.ones(n_insider), np.full(n_script, 2)].astype(int)
    idx = r.permutation(len(y))
    return X[idx], y[idx]


def scale(X):
    """log velocity and cyclic time so midnight is next to 23:59."""
    t = X[:, 0] / 24 * 2 * np.pi
    return np.c_[np.sin(t), np.cos(t), np.log1p(X[:, 1]), X[:, 2]]


def evaluate(seed=42, hard=False, contamination=0.05):
    X, y = generate(seed, hard)
    cut = int(len(y) * .7)
    Xtr, Xte, ytr, yte = X[:cut], X[cut:], y[:cut], y[cut:]
    model = IsolationForest(n_estimators=300, contamination=contamination, random_state=seed).fit(scale(Xtr))
    pred = (model.predict(scale(Xte)) == -1).astype(int)            # 1 = flagged
    true = (yte > 0).astype(int)
    tn, fp, fn, tp = confusion_matrix(true, pred, labels=[0, 1]).ravel()
    prec = tp / (tp + fp) if tp + fp else 0.0; rec = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0.0
    per = {name: dict(n=int((yte == k).sum()), caught=int(((yte == k) & (pred == 1)).sum())) for k, name in ((1, "insider_abuse"), (2, "script_exploit"))}
    for v in per.values(): v["recall"] = round(v["caught"] / v["n"], 4) if v["n"] else None
    return dict(variant="hard" if hard else "spec", seed=seed, train=int(len(ytr)), test=int(len(yte)),
                test_normal=int((yte == 0).sum()), test_anomalous=int((yte > 0).sum()),
                confusion=dict(TP=int(tp), FP=int(fp), FN=int(fn), TN=int(tn)),
                precision=round(prec, 4), recall=round(rec, 4), f1=round(f1, 4), false_alarm_rate=round(fp / max(1, fp + tn), 4), per_stratum=per)


def repeated(hard=False, seeds=range(10)):
    rows = [evaluate(s, hard) for s in seeds]
    m = lambda k: round(float(np.mean([r[k] for r in rows])), 4)
    sd = lambda k: round(float(np.std([r[k] for r in rows])), 4)
    return dict(variant=rows[0]["variant"], runs=len(rows), precision_mean=m("precision"), precision_sd=sd("precision"), recall_mean=m("recall"), recall_sd=sd("recall"),
                f1_mean=m("f1"), f1_sd=sd("f1"), first_run=rows[0])
