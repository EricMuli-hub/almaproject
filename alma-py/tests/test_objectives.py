"""One group of tests per specific objective (O1 to O5) plus an end to end flow."""
import json, time
from sqlalchemy import select, delete
from eth_account import Account
from app.db import User, Credential, Batch, Anomaly, AuditLog, KeyVault, Institution
from app.core import unhx
from app.chain import TxResult
from app.ai import evaluate

REC = {"student_no": "S-001", "name": "Amina Wanjiru", "award": "BSc Computer Science", "class": "First Class Honours", "year": 2025}


def issue(c, h, em="amina@mail.test", rec=None, who="adminA"):
    r = c.post("/institution/credentials", json={"holder_email": em, "record": rec or REC, "label": "Degree"}, headers=h[who]); assert r.status_code == 200, r.text
    return r.json()


def user(core, email):
    with core.Session() as db: return db.execute(select(User).where(User.email == email.lower())).scalar()


# ============ O1: smart-contract RBAC ============
def test_o1_api_roles_enforced(world):
    c, h = world
    assert c.post("/institution/credentials", json={"holder_email": "amina@mail.test", "record": REC}, headers=h["amina"]).status_code == 403
    assert c.post("/institution/credentials", json={"holder_email": "amina@mail.test", "record": REC}, headers=h["emp"]).status_code == 403
    assert c.post("/admin/institutions", json={"name": "X", "admin_email": "x@x.test", "password": "password-123"}, headers=h["adminA"]).status_code == 403
    assert c.get("/regulator/stats", headers=h["amina"]).status_code == 403
    assert c.get("/regulator/stats").status_code == 401


def test_o1_contract_refuses_without_role(world):
    """Skip the API entirely and talk to the contract: it must still say no."""
    c, h = world; core = c.core
    stranger = Account.create(); core.chain.fund(stranger.address)
    r = core.chain.tx("anchorBatch", stranger.key, b"\x07" * 32, 5, "Qm")
    assert not r.ok and "NotAllowed" in r.error
    stu = user(core, "amina@mail.test")
    r = core.chain.tx("issueCredential", core.key_of(stu), b"\x08" * 32, stu.address, "Qm")
    assert not r.ok and "NotAllowed" in r.error
    emp = user(core, "hr@firm.test")
    r = core.chain.tx("anchorBatch", core.key_of(emp), b"\x09" * 32, 5, "Qm")
    assert not r.ok and "UniversityAdmin" in r.error
    adm = user(core, "adminA@uni.test")
    r = core.chain.tx("registerEmployer", core.key_of(adm), Account.create().address)
    assert not r.ok and "PlatformAdmin" in r.error


def test_o1_institution_cannot_touch_anothers_records(world):
    c, h = world; core = c.core
    out = issue(c, h)
    admB = user(core, "adminB@uni.test")
    r = core.chain.tx("revokeCredential", core.key_of(admB), unhx(out["leaf"]))
    assert not r.ok and "WrongInstitution" in r.error
    assert c.post(f"/institution/credentials/{out['credential_id']}/revoke", headers=h["adminB"]).status_code == 403
    # and B cannot issue to A's student
    r = c.post("/institution/credentials", json={"holder_email": "amina@mail.test", "record": REC}, headers=h["adminB"]); assert r.status_code == 400


def test_o1_regulator_suspends_and_issuing_stops(world):
    c, h = world
    assert issue(c, h)["credential_id"]
    iid = c.get("/regulator/stats", headers=h["reg"]).json()["institutions"][0]["id"]
    assert c.post(f"/regulator/institutions/{iid}/status", json={"active": False, "reason": "audit"}, headers=h["reg"]).status_code == 200
    r = c.post("/institution/credentials", json={"holder_email": "amina@mail.test", "record": REC}, headers=h["adminA"]); assert r.status_code == 403
    core = c.core; adm = user(core, "adminA@uni.test")
    r = core.chain.tx("anchorBatch", core.key_of(adm), b"\x0a" * 32, 1, "Qm")
    assert not r.ok and "InstitutionInactive" in r.error
    assert c.post(f"/regulator/institutions/{iid}/status", json={"active": True}, headers=h["reg"]).status_code == 200
    assert issue(c, h, rec={**REC, "year": 2026})["credential_id"]


# ============ O2: AI anomaly detection ============
def test_o2_model_detects_attack_patterns_with_few_false_alarms():
    r = evaluate(seed=11)
    assert r["detected"] == 4, r["attacks"]
    assert r["false_alarm_rate"] < 0.03, r
    limit = {"burst_offhours": 20, "unauthorized_attempts": 5, "revocation_storm": 12, "mass_batch_offhours": 1}
    for k, v in r["attacks"].items(): assert v["detected_at_event"] is not None and v["detected_at_event"] <= limit[k], (k, v)


def test_o2_realtime_flag_and_automatic_hold(world):
    c, h = world; core = c.core
    adm = user(core, "adminA@uni.test")
    with core.Session() as db:
        for _ in range(7):   # a compromised admin key probing forbidden actions
            core._chain_call(db, adm, "registerEmployer", Account.create().address)
        an = db.execute(select(Anomaly)).scalars().all()
        assert any(a.severity == "critical" for a in an)
        inst = db.get(Institution, adm.institution_id)
        assert inst.status == "held"
    assert core.chain.c.functions.institutions(1).call()[2] is False       # held on chain too
    r = c.post("/institution/credentials", json={"holder_email": "amina@mail.test", "record": REC}, headers=h["adminA"]); assert r.status_code == 403
    items = c.get("/regulator/anomalies", headers=h["reg"]).json()
    assert items and items[0]["reasons"]
    assert c.post(f"/regulator/anomalies/{items[0]['id']}/confirmed", headers=h["reg"]).status_code == 200


def test_o2_normal_work_is_not_flagged(world):
    c, h = world
    for i in range(6): issue(c, h, rec={**REC, "year": 2000 + i})
    assert c.get("/regulator/anomalies", headers=h["reg"]).json() == []


def test_o2_issuing_burst_is_flagged(world):
    c, h = world; core = c.core; adm = user(core, "adminA@uni.test")
    with core.Session() as db:
        inst = db.get(Institution, adm.institution_id)
        for i in range(60): core._event(db, adm.address, inst.chain_id, "issueCredential", TxResult(True), 1)
        db.commit(); assert db.execute(select(Anomaly)).scalars().all()


# ============ O3: IPFS style storage plus hashing ============
def test_o3_records_are_encrypted_and_content_addressed(world):
    c, h = world; core = c.core
    out = issue(c, h)
    raw = core.store.get(out["record_cid"])
    assert b"Amina" not in raw and b"Computer Science" not in raw
    path = core.store.dir / out["record_cid"]
    path.write_bytes(raw + b"x")                 # malicious tampering outside the server
    try: core.store.get(out["record_cid"]); assert False
    except ValueError: pass


def test_o3_verification_and_recovery_survive_database_loss(world):
    c, h = world; core = c.core
    items = [{"holder_email": "amina@mail.test", "record": {**REC, "n": i}, "label": "Transcript"} for i in range(20)]
    out = c.post("/institution/credentials/batch", json={"items": items}, headers=h["adminA"]).json()
    cid = out["credential_ids"][3]
    pkg = c.get(f"/student/credentials/{cid}/package", headers=h["amina"]).json()
    leaf = pkg["leaf"]
    with core.Session() as db:                    # the central server's index is destroyed
        db.execute(delete(Credential)); db.execute(delete(Batch)); db.commit()
    assert c.post("/verify/package", json={k: pkg[k] for k in ("record", "salt", "proof", "root")}).json()["valid"] is True   # needs only the chain
    with core.Session() as db: assert core.recover_index(db)["rebuilt_credentials"] == 20
    rid = "ALM-" + leaf[2:14].upper()
    v = c.get(f"/verify/{rid}").json(); assert v["valid"] is True, v


def test_o3_tampered_record_fails_verification(world):
    c, h = world
    out = c.post("/institution/credentials/batch", json={"items": [{"holder_email": "amina@mail.test", "record": {**REC, "n": i}} for i in range(8)]}, headers=h["adminA"]).json()
    pkg = c.get(f"/student/credentials/{out['credential_ids'][0]}/package", headers=h["amina"]).json()
    ok = {k: pkg[k] for k in ("record", "salt", "proof", "root")}
    assert c.post("/verify/package", json=ok).json()["valid"]
    bad = {**ok, "record": {**pkg["record"], "class": "Pass"}}
    assert c.post("/verify/package", json=bad).json()["valid"] is False


def test_o3_revocation_inside_a_batch(world):
    c, h = world
    out = c.post("/institution/credentials/batch", json={"items": [{"holder_email": "amina@mail.test", "record": {**REC, "n": i}} for i in range(5)]}, headers=h["adminA"]).json()
    a, b = out["credential_ids"][:2]
    assert c.get(f"/verify/{a}").json()["valid"]
    assert c.post(f"/institution/credentials/{a}/revoke", headers=h["adminA"]).status_code == 200
    assert c.get(f"/verify/{a}").json()["valid"] is False and c.get(f"/verify/{b}").json()["valid"] is True


# ============ O4: privacy and data sovereignty ============
def test_o4_no_personal_data_on_chain(world):
    c, h = world
    issue(c, h); c.post("/institution/credentials/batch", json={"items": [{"holder_email": "brian@mail.test", "record": {**REC, "name": "Brian Otieno"}}]}, headers=h["adminA"])
    r = c.get("/system/privacy/chain-check", headers=h["reg"]).json()
    assert r["personal_data_found_on_chain"] is False and r["checked_logs"]
    assert "amina" not in c.core.chain.all_logs_text()


def test_o4_disclosure_needs_consent_and_can_be_withdrawn(world):
    c, h = world
    cid = issue(c, h)["credential_id"]
    assert c.get(f"/employer/credentials/{cid}", headers=h["emp"]).status_code == 403
    assert c.post(f"/student/credentials/{cid}/consent", json={"verifier_email": "hr@firm.test", "days": 7, "purpose": "job offer"}, headers=h["brian"]).status_code == 403   # not his record
    assert c.post(f"/student/credentials/{cid}/consent", json={"verifier_email": "hr@firm.test", "days": 7, "purpose": "job offer"}, headers=h["amina"]).status_code == 200
    d = c.get(f"/employer/credentials/{cid}", headers=h["emp"]); assert d.status_code == 200 and d.json()["record"]["award"] == "BSc Computer Science" and d.json()["verification"]["valid"]
    assert c.delete(f"/student/credentials/{cid}/consent/hr@firm.test", headers=h["amina"]).status_code == 200
    assert c.get(f"/employer/credentials/{cid}", headers=h["emp"]).status_code == 403


def test_o4_consent_expires(world):
    c, h = world
    cid = issue(c, h)["credential_id"]
    assert c.post(f"/student/credentials/{cid}/consent", json={"verifier_email": "hr@firm.test", "days": -1}, headers=h["amina"]).status_code == 200
    assert c.get(f"/employer/credentials/{cid}", headers=h["emp"]).status_code == 403


def test_o4_public_verification_leaks_nothing_personal(world):
    c, h = world
    cid = issue(c, h)["credential_id"]; v = c.get(f"/verify/{cid}").json()
    assert v["valid"] and v["issuer"] == "University A"
    blob = json.dumps(v).lower(); assert "amina" not in blob and "s-001" not in blob and "first class" not in blob


def test_o4_right_to_erasure_by_key_destruction(world):
    c, h = world; core = c.core
    cid = issue(c, h)["credential_id"]
    assert c.post(f"/student/credentials/{cid}/consent", json={"verifier_email": "hr@firm.test"}, headers=h["amina"]).status_code == 200
    r = c.delete(f"/student/credentials/{cid}", headers=h["amina"]).json(); assert r["erased"] and r["key_destroyed"]
    with core.Session() as db: assert db.get(KeyVault, cid) is None
    assert c.get(f"/employer/credentials/{cid}", headers=h["emp"]).status_code == 410
    v = c.get(f"/verify/{cid}").json(); assert v["valid"] is False and "erased" in v["reason"]
    assert c.get(f"/student/credentials/{cid}/package", headers=h["amina"]).status_code == 410


def test_o4_data_portability_export(world):
    c, h = world
    issue(c, h)
    ex = c.get("/student/export", headers=h["amina"]).json()
    assert ex["profile"]["email"] == "amina@mail.test" and ex["credentials"][0]["record"]["award"] == "BSc Computer Science" and ex["region"]


def test_o4_audit_trail_is_tamper_evident(world):
    c, h = world; core = c.core
    issue(c, h)
    assert c.get("/system/audit/verify", headers=h["reg"]).json()["intact"] is True
    with core.Session() as db:
        row = db.execute(select(AuditLog).where(AuditLog.action == "issued_single")).scalar(); row.detail = "ALM-FORGED"; db.commit()
    assert c.get("/system/audit/verify", headers=h["reg"]).json()["intact"] is False


# ============ O5: performance, scalability, cost ============
def test_o5_batch_anchoring_makes_cost_per_record_collapse(world):
    c, h = world
    single = issue(c, h)["gas"]
    out = c.post("/institution/credentials/batch", json={"items": [{"holder_email": "amina@mail.test", "record": {**REC, "n": i}} for i in range(300)]}, headers=h["adminA"]).json()
    a = out["anchors"][0]; assert a["count"] == 300
    assert a["gas_per_record"] < single / 100, (single, a)


def test_o5_one_transaction_for_thousands_and_all_verify(world):
    c, h = world; core = c.core; adm = user(core, "adminA@uni.test")
    items = [{"holder_email": "amina@mail.test", "record": {**REC, "n": i}} for i in range(2500)]
    t = time.time()
    with core.Session() as db: out = core.issue_batch(db, adm, items)
    took = time.time() - t
    assert len(out["anchors"]) == 1 and out["anchors"][0]["count"] == 2500
    assert took < 60, took
    import random
    for cid in random.sample(out["credential_ids"], 25): assert c.get(f"/verify/{cid}").json()["valid"]
    with core.Session() as db:
        p = core.proof_for(db, db.get(Credential, out["credential_ids"][100])); assert len(p["proof"]) == 12   # log2(2500) rounded up


def test_o5_large_batches_are_split_automatically(world):
    c, h = world; core = c.core; core.s.max_batch = 100
    items = [{"holder_email": "amina@mail.test", "record": {**REC, "n": i}} for i in range(250)]
    out = c.post("/institution/credentials/batch", json={"items": items}, headers=h["adminA"]).json()
    assert [a["count"] for a in out["anchors"]] == [100, 100, 50]


def test_o5_concurrent_verification(world):
    c, h = world
    ids = c.post("/institution/credentials/batch", json={"items": [{"holder_email": "amina@mail.test", "record": {**REC, "n": i}} for i in range(50)]}, headers=h["adminA"]).json()["credential_ids"]
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(8) as ex: res = list(ex.map(lambda i: c.get(f"/verify/{i}").json()["valid"], ids * 4))
    assert all(res) and len(res) == 200


def test_o5_benchmark_module(api):
    from app.bench import quick
    r = quick(api.core)
    assert r["gas"]["batch_1000_per_record"] < r["gas"]["single_issue"] / 50
    assert r["merkle"]["100000"]["build_s"] < 30 and r["verify"]["hybrid_p50_ms"] > 0 and r["verify"]["central_p50_ms"] > 0


# ============ end to end ============
def test_end_to_end(world):
    c, h = world
    assert c.get("/system/health").json()["ok"]
    out = issue(c, h); cid = out["credential_id"]
    assert c.get("/student/credentials", headers=h["amina"]).json()[0]["status"] == "issued"
    assert c.get(f"/verify/{cid}").json()["valid"]
    assert c.get("/regulator/stats", headers=h["reg"]).json()["credentials"] == 1
    assert c.get("/admin/employers/pending", headers=h["owner"]).json() == []
