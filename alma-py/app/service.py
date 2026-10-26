"""Business logic. Every action is checked twice: here (JWT role) and again by the smart contract
(msg.sender role), so a bug or a stolen API token still cannot issue or revoke without the right chain role."""
import json, secrets, threading, time
from functools import lru_cache
from eth_account import Account
from sqlalchemy import select, func, delete

from .core import (Settings, make_store, canonical, leaf_hash, hx, unhx, merkle_levels, merkle_proof, verify_proof,
                   aes_encrypt, aes_decrypt, hash_password, check_password, sha, now)
from .chain import Chain
from .db import (make_engine, User, Institution, Batch, Credential, KeyVault, LedgerEvent, Anomaly, Consent, AuditLog)
from .ai import Monitor


class Denied(Exception):
    def __init__(self, msg, code=403): super().__init__(msg); self.code = code


class NotFound(Denied):
    def __init__(self, msg="not found"): super().__init__(msg, 404)


class App:
    def __init__(self, settings: Settings | None = None):
        self.s = settings or Settings()
        self.engine, self.Session = make_engine(self.s.database_url)
        self.store = make_store(self.s)
        pk = self._load_platform_key()
        self.chain = Chain(self.s.rpc_url, self.s.contract_address, self.s.funder_key, pk)
        self.monitor = Monitor(self.s.data_dir)
        self.mk = self.s.master_key
        self._tree_cache = {}; self._rc = {}
        if self.s.batch_window_s > 0: threading.Thread(target=self._batcher, daemon=True).start()
        if self.s.watcher:
            from .watcher import Watcher
            self.watcher = Watcher(self).start()

    # ---------- keys ----------
    def _load_platform_key(self):
        import pathlib
        p = pathlib.Path(self.s.data_dir) / "platform.key"
        if self.s.rpc_url:                       # real network: key must be supplied, never generated silently
            return __import__("os").getenv("PLATFORM_KEY", "")
        return ""

    def wrap(self, raw: bytes) -> bytes: return aes_encrypt(self.mk, raw)
    def unwrap(self, blob: bytes) -> bytes: return aes_decrypt(self.mk, blob)
    def key_of(self, u: User) -> bytes: return self.unwrap(u.key_enc)

    # ---------- audit (hash chained, tamper evident) ----------
    def audit(self, db, actor, action, detail=""):
        last = db.execute(select(AuditLog).order_by(AuditLog.id.desc()).limit(1)).scalar()
        prev = last.hash if last else "0" * 64
        ts = now(); body = json.dumps([ts, actor, action, detail, prev])
        db.add(AuditLog(ts=ts, actor=actor, action=action, detail=detail, prev=prev, hash=sha(body.encode()).hex()))

    def verify_audit_chain(self, db):
        prev = "0" * 64
        for r in db.execute(select(AuditLog).order_by(AuditLog.id)).scalars():
            if r.prev != prev or sha(json.dumps([r.ts, r.actor, r.action, r.detail, r.prev]).encode()).hex() != r.hash:
                return {"intact": False, "broken_at": r.id}
            prev = r.hash
        return {"intact": True, "entries": db.execute(select(func.count(AuditLog.id))).scalar()}

    # ---------- users ----------
    def _new_user(self, db, email, name, role, password="", status="active", inst_id=None, key=None, fund=True):
        if db.execute(select(User).where(User.email == email.lower())).scalar(): raise Denied("email already in use", 409)
        acct = Account.from_key(key) if key else Account.create()
        if fund: self.chain.fund(acct.address, 5)
        u = User(email=email.lower(), name=name, role=role, pw=hash_password(password) if password else "", address=acct.address,
                 key_enc=self.wrap(bytes(acct.key)), institution_id=inst_id, status=status, created=now())
        db.add(u); db.flush(); return u

    def ensure_platform_admin(self, db, email, password):
        u = db.execute(select(User).where(User.role == "platform_admin")).scalar()
        if u: return u
        u = self._new_user(db, email, "Platform owner", "platform_admin", password, key=bytes(self.chain.platform.key), fund=False)
        self.audit(db, email, "bootstrap", "platform admin created"); db.commit(); return u

    def login(self, db, email, password):
        u = db.execute(select(User).where(User.email == email.lower())).scalar()
        if not u or not u.pw or not check_password(password, u.pw): raise Denied("wrong email or password", 401)
        if u.status != "active": raise Denied(f"account is {u.status}", 403)
        return u

    def _event(self, db, actor_addr, inst_chain_id, name, res, size=1, ts=None, entropy=0.0, source="api"):
        """Write the action to the ledger-event table and score it with the AI monitor in real time."""
        ev = dict(ts=ts or now(), name=name, success=bool(res.ok), size=size, error=res.error or "", entropy=entropy)
        rows = db.execute(select(LedgerEvent).where(LedgerEvent.actor == actor_addr, LedgerEvent.ts >= ev["ts"] - 86400, LedgerEvent.ts <= ev["ts"])
                          .order_by(LedgerEvent.ts)).scalars().all()
        hist = [dict(ts=r.ts, name=r.name, success=r.success, size=r.size, error=r.error) for r in rows]
        db.add(LedgerEvent(ts=ev["ts"], actor=actor_addr, inst_id=inst_chain_id, name=name, success=ev["success"], size=size,
                           error=ev["error"], tx_hash=res.tx_hash, gas=res.gas, entropy=entropy, source=source))
        a = self.monitor.assess(hist, ev)
        if a["severity"] != "none":
            an = Anomaly(ts=ev["ts"], actor=actor_addr, inst_id=inst_chain_id, score=a["score"], severity=a["severity"],
                         reasons="; ".join(a["reasons"]))
            inst = db.execute(select(Institution).where(Institution.chain_id == inst_chain_id)).scalar() if inst_chain_id else None
            if a["severity"] == "critical" and self.s.auto_hold and inst:
                r = self.chain.tx("setInstitutionStatus", self.chain.platform.key, inst_chain_id, False, True, "AI hold: " + an.reasons[:80])
                if r.ok: inst.status = "held"; inst.flagged = True; an.action = "institution put on hold on chain until a regulator reviews it"
            elif a["severity"] == "high" and self.s.auto_hold and inst and not inst.flagged:
                r = self.chain.tx("setInstitutionStatus", self.chain.platform.key, inst_chain_id, True, True, "AI flag: " + an.reasons[:80])
                if r.ok: inst.flagged = True; an.action = "institution flagged on chain for regulator attention (issuing continues)"
            db.add(an)
            self.audit(db, actor_addr, "anomaly", f'{a["severity"]} {a["score"]}: {an.reasons}')
        return a

    def _chain_call(self, db, user, fn, *args, inst_chain_id=None, size=1, event_name=None):
        res = self.chain.tx(fn, self.key_of(user), *args)
        self._event(db, user.address, inst_chain_id or self._inst_chain_id(db, user), event_name or fn, res, size)
        db.commit()
        return res

    def _inst_chain_id(self, db, u):
        if not u.institution_id: return None
        i = db.get(Institution, u.institution_id); return i.chain_id if i else None

    # ---------- onboarding ----------
    def create_institution(self, db, admin_user, name, admin_email, password):
        if admin_user.role != "platform_admin": raise Denied("only the platform owner registers institutions")
        u = self._new_user(db, admin_email, name + " administrator", "university_admin", password)
        res = self.chain.tx("registerInstitution", self.key_of(admin_user), u.address, name)
        self._event(db, admin_user.address, None, "registerInstitution", res)
        if not res.ok: db.rollback(); raise Denied("chain refused: " + res.error)
        cid = self.chain.c.functions.instOfAdmin(u.address).call()
        inst = Institution(chain_id=cid, name=name, admin_user_id=u.id, status="active"); db.add(inst); db.flush()
        u.institution_id = inst.id
        self.audit(db, admin_user.email, "institution_created", f"{name} (chain id {cid})"); db.commit(); return inst

    def create_regulator(self, db, admin_user, email, name, password):
        if admin_user.role != "platform_admin": raise Denied("only the platform owner registers regulators")
        u = self._new_user(db, email, name, "regulator", password)
        res = self.chain.tx("registerRegulator", self.key_of(admin_user), u.address)
        self._event(db, admin_user.address, None, "registerRegulator", res)
        if not res.ok: db.rollback(); raise Denied("chain refused: " + res.error)
        self.audit(db, admin_user.email, "regulator_created", email); db.commit(); return u

    def register_employer(self, db, email, name, password):
        u = self._new_user(db, email, name, "employer", password, status="pending", fund=False)
        self.audit(db, email, "employer_registered", "waiting for approval"); db.commit(); return u

    def approve_employer(self, db, admin_user, employer_id):
        if admin_user.role != "platform_admin": raise Denied("only the platform owner approves employers")
        u = db.get(User, employer_id)
        if not u or u.role != "employer": raise NotFound()
        self.chain.fund(u.address, 2)
        res = self.chain.tx("registerEmployer", self.key_of(admin_user), u.address)
        self._event(db, admin_user.address, None, "registerEmployer", res)
        if not res.ok: raise Denied("chain refused: " + res.error)
        u.status = "active"; self.audit(db, admin_user.email, "employer_approved", u.email); db.commit(); return u

    def add_student(self, db, inst_user, email, name):
        if inst_user.role != "university_admin": raise Denied("only an institution administrator adds students")
        u = self._new_user(db, email, name, "student", status="invited", inst_id=inst_user.institution_id)
        u.invite = secrets.token_urlsafe(9)
        res = self._chain_call(db, inst_user, "registerStudent", u.address)
        if not res.ok: db.rollback(); raise Denied("chain refused: " + res.error)
        self.audit(db, inst_user.email, "student_added", email); db.commit(); return u

    def activate(self, db, email, invite, password):
        u = db.execute(select(User).where(User.email == email.lower())).scalar()
        if not u or u.status != "invited" or not secrets.compare_digest(u.invite or "x", invite): raise Denied("invalid invitation", 400)
        u.pw = hash_password(password); u.status = "active"; u.invite = ""; db.commit(); return u

    # ---------- issuing ----------
    def _package(self, db, inst_user, holder_email, record, label, cache=None):
        if inst_user.role != "university_admin": raise Denied("only an institution administrator issues records")
        cache = cache if cache is not None else {}
        if "inst" not in cache:
            cache["inst"] = db.get(Institution, inst_user.institution_id)
        inst = cache["inst"]
        if inst.status != "active": raise Denied(f"institution is {inst.status}; issuing is paused")
        key = holder_email.lower()
        if key not in cache:
            cache[key] = db.execute(select(User).where(User.email == key, User.role == "student",
                                                       User.institution_id == inst_user.institution_id)).scalar()
        holder = cache[key]
        if not holder: raise Denied("student is not registered at this institution", 400)
        salt = secrets.token_bytes(16); leaf = leaf_hash(record, salt)
        dek = secrets.token_bytes(32)
        blob = aes_encrypt(dek, canonical({"record": record, "salt": salt.hex(), "issuer": inst.name}))
        cid = "ALM-" + secrets.token_hex(6).upper()
        db.add(KeyVault(credential_id=cid, dek_enc=self.wrap(dek), created=now()))
        return holder, inst, leaf, blob, cid

    def issue_single(self, db, inst_user, holder_email, record, label="Record"):
        holder, inst, leaf, blob, cid = self._package(db, inst_user, holder_email, record, label)
        rcid = self.store.put(blob)
        res = self._chain_call(db, inst_user, "issueCredential", leaf, holder.address, rcid)
        if not res.ok: db.rollback(); raise Denied("chain refused: " + res.error)
        db.add(Credential(id=cid, inst_id=inst.id, holder_id=holder.id, kind="single", leaf=hx(leaf), record_cid=rcid,
                          status="issued", kind_label=label, issued_at=now()))
        self.audit(db, inst_user.email, "issued_single", cid); db.commit()
        return dict(credential_id=cid, leaf=hx(leaf), record_cid=rcid, gas=res.gas, tx=res.tx_hash)

    def queue(self, db, inst_user, holder_email, record, label="Record", commit=True, _cache=None):
        holder, inst, leaf, blob, cid = self._package(db, inst_user, holder_email, record, label, _cache)
        db.add(Credential(id=cid, inst_id=inst.id, holder_id=holder.id, kind="batch", leaf=hx(leaf), queued_blob=blob,
                          status="queued", kind_label=label))
        if commit: db.commit()
        return dict(credential_id=cid, status="queued")

    def flush(self, db, inst_user):
        """Anchor every queued credential of the institution. One chain transaction per batch (max_batch records)."""
        inst = db.get(Institution, inst_user.institution_id)
        if inst.status != "active": raise Denied(f"institution is {inst.status}; issuing is paused")
        out = []
        while True:
            q = db.execute(select(Credential).where(Credential.inst_id == inst.id, Credential.status == "queued")
                           .order_by(Credential.leaf).limit(self.s.max_batch)).scalars().all()
            if not q: break
            leaves = [unhx(c.leaf) for c in q]
            levels = merkle_levels(leaves); root = levels[-1][0]
            manifest = canonical({"v": 1, "institution": inst.chain_id, "count": len(leaves), "root": hx(root), "leaves": [c.leaf for c in q]})
            mcid = self.store.put(manifest)
            res = self._chain_call(db, inst_user, "anchorBatch", root, len(leaves), mcid, size=len(leaves))
            if not res.ok: raise Denied("chain refused: " + res.error)
            b = Batch(root=hx(root), inst_id=inst.id, count=len(leaves), manifest_cid=mcid, tx_hash=res.tx_hash, gas=res.gas, anchored_at=now())
            db.add(b); db.flush()
            for i, c in enumerate(q):
                c.record_cid = self.store.put(c.queued_blob); c.queued_blob = None
                c.batch_id = b.id; c.leaf_index = i; c.status = "issued"; c.issued_at = now()
            self._rc.clear()
            self.audit(db, inst_user.email, "batch_anchored", f"{len(q)} records, root {hx(root)}"); db.commit()
            out.append(dict(root=hx(root), count=len(q), gas=res.gas, gas_per_record=round(res.gas / len(q), 1), manifest_cid=mcid, tx=res.tx_hash))
        return out

    def issue_batch(self, db, inst_user, items):
        cache = {}
        ids = [self.queue(db, inst_user, i["holder_email"], i["record"], i.get("label", "Record"), commit=False, _cache=cache)["credential_id"] for i in items]
        db.commit()
        return dict(credential_ids=ids, anchors=self.flush(db, inst_user))

    def _batcher(self):
        while True:
            time.sleep(self.s.batch_window_s)
            try:
                with self.Session() as db:
                    for u in db.execute(select(User).where(User.role == "university_admin")).scalars():
                        if db.execute(select(func.count(Credential.id)).where(Credential.inst_id == u.institution_id, Credential.status == "queued")).scalar():
                            self.flush(db, u)
            except Exception: pass

    def revoke(self, db, inst_user, cred_id):
        c = self._cred(db, cred_id)
        if inst_user.role != "university_admin" or c.inst_id != inst_user.institution_id: raise Denied("not your institution's record")
        if c.status != "issued": raise Denied(f"record is {c.status}", 409)
        if c.kind == "single": res = self._chain_call(db, inst_user, "revokeCredential", unhx(c.leaf), event_name="revokeCredential")
        else:
            b = db.get(Batch, c.batch_id); res = self._chain_call(db, inst_user, "revokeLeaf", unhx(b.root), unhx(c.leaf), event_name="revokeLeaf")
        if not res.ok: raise Denied("chain refused: " + res.error)
        self._rc.clear()
        c.status = "revoked"; self.audit(db, inst_user.email, "revoked", cred_id); db.commit(); return dict(credential_id=cred_id, status="revoked", tx=res.tx_hash)

    def _rd(self, key, fn):
        """Short lived cache for chain reads (set READ_CACHE_TTL). Off by default so revocations show at once."""
        ttl = self.s.read_cache_ttl
        if ttl <= 0: return fn()
        hit = self._rc.get(key); t = time.time()
        if hit and t - hit[0] < ttl: return hit[1]
        val = fn(); self._rc[key] = (t, val)
        if len(self._rc) > 20000: self._rc.clear()
        return val

    # ---------- verification ----------
    def _cred(self, db, cid):
        c = db.get(Credential, cid)
        if not c: raise NotFound("credential not found")
        return c

    def _levels(self, root, leaves):
        lv = self._tree_cache.get(root)
        if lv is None:
            lv = merkle_levels(leaves)
            if len(self._tree_cache) > 64: self._tree_cache.pop(next(iter(self._tree_cache)))
            self._tree_cache[root] = lv
        return lv

    def _batch_leaves(self, db, b):
        rows = db.execute(select(Credential.leaf).where(Credential.batch_id == b.id).order_by(Credential.leaf_index)).all()
        return [unhx(r[0]) for r in rows]

    def proof_for(self, db, c):
        if c.kind != "batch" or c.batch_id is None: return None
        b = db.get(Batch, c.batch_id)
        return dict(root=b.root, proof=merkle_proof(self._levels(b.root, self._batch_leaves(db, b)), c.leaf_index), index=c.leaf_index)

    def verify(self, db, cred_id):
        """Public check. Answers valid or not and who issued it. It never returns personal data."""
        c = db.get(Credential, cred_id)
        if not c: return dict(found=False, valid=False, reason="no such credential")
        inst = db.get(Institution, c.inst_id)
        base = dict(found=True, credential_id=c.id, issuer=inst.name if inst else None, type=c.kind_label, issued_at=c.issued_at, anchored=c.kind, status=c.status)
        if c.status == "erased": return {**base, "valid": False, "reason": "the holder had this record erased"}
        if c.status == "queued": return {**base, "valid": False, "reason": "waiting to be anchored on the ledger"}
        checks = {}
        if c.kind == "single":
            st = self._rd(("cs", c.leaf), lambda: self.chain.credential_status(c.leaf))
            checks = dict(on_chain=st["exists"], not_revoked=not st["revoked"], issuer_active=st["issuer_active"])
        else:
            b = db.get(Batch, c.batch_id); p = self.proof_for(db, c)
            st = self._rd(("bs", b.root), lambda: self.chain.batch_status(b.root))
            checks = dict(on_chain=st["exists"], merkle_proof=verify_proof(unhx(c.leaf), p["proof"], unhx(b.root)),
                          batch_not_revoked=not st["revoked"], not_revoked=not self._rd(("lr", c.leaf), lambda: self.chain.leaf_revoked(c.leaf)), issuer_active=st["issuer_active"])
        ok = all(checks.values())
        reason = "" if ok else "failed: " + ", ".join(k for k, v in checks.items() if not v)
        return {**base, "valid": ok, "checks": checks, "reason": reason}

    def verify_package(self, pkg):
        """Offline package held by the student: record, salt and Merkle proof. Needs only the chain."""
        leaf = leaf_hash(pkg["record"], bytes.fromhex(pkg["salt"]))
        if pkg.get("proof") is not None:
            root = pkg["root"]; st = self.chain.batch_status(root)
            checks = dict(on_chain=st["exists"], merkle_proof=verify_proof(leaf, pkg["proof"], unhx(root)), batch_not_revoked=not st["revoked"],
                          not_revoked=not self.chain.leaf_revoked(hx(leaf)), issuer_active=st["issuer_active"])
        else:
            st = self.chain.credential_status(hx(leaf))
            checks = dict(on_chain=st["exists"], not_revoked=not st["revoked"], issuer_active=st["issuer_active"])
        return dict(valid=all(checks.values()), checks=checks, leaf=hx(leaf))

    def package_for(self, db, user, cred_id):
        c = self._cred(db, cred_id)
        if c.holder_id != user.id: raise Denied("not your record")
        data = self._open(db, c)
        pr = self.proof_for(db, c)
        return dict(credential_id=c.id, record=data["record"], salt=data["salt"], issuer=data["issuer"],
                    proof=pr["proof"] if pr else None, root=pr["root"] if pr else None, leaf=c.leaf)

    def _open(self, db, c):
        if c.status == "erased": raise Denied("this record was erased", 410)
        v = db.get(KeyVault, c.id)
        if not v: raise Denied("key was destroyed; record is unreadable", 410)
        blob = c.queued_blob if c.status == "queued" else self.store.get(c.record_cid)
        return json.loads(aes_decrypt(self.unwrap(v.dek_enc), blob))

    # ---------- consent and disclosure ----------
    def grant(self, db, student, cred_id, verifier_email, days, purpose):
        c = self._cred(db, cred_id)
        if c.holder_id != student.id: raise Denied("not your record")
        v = db.execute(select(User).where(User.email == verifier_email.lower(), User.role == "employer", User.status == "active")).scalar()
        if not v: raise Denied("no approved employer with that email", 400)
        until = self.chain.now() + int(days * 86400)
        res = self._chain_call(db, student, "grantAccess", unhx(c.leaf), v.address, until, event_name="grantAccess")
        if not res.ok: raise Denied("chain refused: " + res.error)
        db.add(Consent(credential_id=c.id, verifier_id=v.id, purpose=purpose[:200], granted=now(), until=until, tx_hash=res.tx_hash))
        self.audit(db, student.email, "consent_granted", f"{cred_id} -> {verifier_email} ({purpose[:60]})"); db.commit()
        return dict(credential_id=c.id, verifier=verifier_email, until=until, tx=res.tx_hash)

    def revoke_consent(self, db, student, cred_id, verifier_email):
        c = self._cred(db, cred_id)
        if c.holder_id != student.id: raise Denied("not your record")
        v = db.execute(select(User).where(User.email == verifier_email.lower())).scalar()
        if not v: raise NotFound()
        res = self._chain_call(db, student, "revokeAccess", unhx(c.leaf), v.address, event_name="revokeAccess")
        for cs in db.execute(select(Consent).where(Consent.credential_id == c.id, Consent.verifier_id == v.id, Consent.revoked == 0)).scalars(): cs.revoked = now()
        self.audit(db, student.email, "consent_revoked", f"{cred_id} -> {verifier_email}"); db.commit()
        return dict(revoked=True, ok=res.ok)

    def disclose(self, db, employer, cred_id):
        c = self._cred(db, cred_id)
        if employer.role != "employer": raise Denied("only approved employers can request a disclosure")
        if not self.chain.has_access(c.leaf, employer.address):
            self.audit(db, employer.email, "disclosure_denied", cred_id); db.commit()
            raise Denied("the holder has not given you access (or it expired)")
        data = self._open(db, c)
        self.audit(db, employer.email, "disclosed", cred_id); db.commit()
        return dict(credential_id=c.id, record=data["record"], issuer=data["issuer"], verification=self.verify(db, cred_id))

    # ---------- data protection ----------
    def export_student(self, db, student):
        out = []
        for c in db.execute(select(Credential).where(Credential.holder_id == student.id)).scalars():
            item = dict(credential_id=c.id, status=c.status, type=c.kind_label)
            if c.status in ("issued", "revoked"): item.update(self.package_for(db, student, c.id))
            out.append(item)
        cons = [dict(credential_id=x.credential_id, verifier_id=x.verifier_id, purpose=x.purpose, until=x.until, revoked=x.revoked)
                for x in db.execute(select(Consent).join(Credential, Credential.id == Consent.credential_id).where(Credential.holder_id == student.id)).scalars()]
        self.audit(db, student.email, "data_export", str(len(out))); db.commit()
        return dict(profile=dict(email=student.email, name=student.name), credentials=out, consents=cons, region=self.s.data_region)

    def erase(self, db, student, cred_id):
        """Right to erasure by crypto-shredding: destroy the record key. The encrypted copy on the content
        store stays (it is immutable) but can never be read again; the on-chain hash is salted and meaningless."""
        c = self._cred(db, cred_id)
        if c.holder_id != student.id: raise Denied("not your record")
        db.execute(delete(KeyVault).where(KeyVault.credential_id == c.id))
        c.status = "erased"; c.queued_blob = None
        removed = False
        p = getattr(self.store, "dir", None)
        if p and c.record_cid and (p / c.record_cid).exists(): (p / c.record_cid).unlink(); removed = True
        for cs in db.execute(select(Consent).where(Consent.credential_id == c.id, Consent.revoked == 0)).scalars(): cs.revoked = now()
        self.audit(db, student.email, "erased", cred_id); db.commit()
        return dict(credential_id=cred_id, erased=True, key_destroyed=True, local_copy_removed=removed)

    def pii_on_chain_check(self, db):
        """Looks for any stored name or email inside everything the contract has ever logged."""
        text = self.chain.all_logs_text().lower()
        hits = []
        for u in db.execute(select(User)).scalars():
            for token in (u.email, u.name):
                if token and token.lower().encode().hex() in text: hits.append(token)
        return dict(personal_data_found_on_chain=bool(hits), checked_logs=True, hits=hits)

    # ---------- regulator ----------
    def set_institution_status(self, db, user, inst_id, active, reason):
        if user.role not in ("regulator", "platform_admin"): raise Denied("regulators only")
        inst = db.get(Institution, inst_id)
        if not inst: raise NotFound()
        res = self._chain_call(db, user, "setInstitutionStatus", inst.chain_id, active, not active, reason[:100], inst_chain_id=inst.chain_id)
        if not res.ok: raise Denied("chain refused: " + res.error)
        self._rc.clear()
        inst.status = "active" if active else "suspended"
        self.audit(db, user.email, "institution_status", f"{inst.name} -> {inst.status}: {reason[:80]}"); db.commit(); return dict(institution=inst.name, status=inst.status)

    def stats(self, db):
        per = []
        for i in db.execute(select(Institution)).scalars():
            n = db.execute(select(func.count(Credential.id)).where(Credential.inst_id == i.id, Credential.status == "issued")).scalar()
            rv = db.execute(select(func.count(Credential.id)).where(Credential.inst_id == i.id, Credential.status == "revoked")).scalar()
            an = db.execute(select(func.count(Anomaly.id)).where(Anomaly.inst_id == i.chain_id)).scalar()
            per.append(dict(id=i.id, name=i.name, status=i.status, issued=n, revoked=rv, anomalies=an))
        gas = db.execute(select(func.coalesce(func.sum(LedgerEvent.gas), 0))).scalar()
        return dict(institutions=per, credentials=db.execute(select(func.count(Credential.id))).scalar(), batches=db.execute(select(func.count(Batch.id))).scalar(),
                    ledger_events=db.execute(select(func.count(LedgerEvent.id))).scalar(), total_gas=int(gas),
                    open_anomalies=db.execute(select(func.count(Anomaly.id)).where(Anomaly.status == "open")).scalar(), store=self.store.kind, region=self.s.data_region)

    # ---------- recovery from the chain and the content store ----------
    def recover_index(self, db):
        """Rebuild batches and credential index rows from chain events plus manifests on the content store.
        Used after the database is lost. Holder links for batch records are not on chain (privacy), so they stay empty."""
        rebuilt = 0
        for ev in self.chain.events("BatchAnchored"):
            root = hx(ev["args"]["root"])
            if db.execute(select(Batch).where(Batch.root == root)).scalar(): continue
            man = json.loads(self.store.get(ev["args"]["manifestCid"]))
            inst = db.execute(select(Institution).where(Institution.chain_id == ev["args"]["instId"])).scalar()
            b = Batch(root=root, inst_id=inst.id if inst else None, count=man["count"], manifest_cid=ev["args"]["manifestCid"], tx_hash=ev["transactionHash"].hex(), gas=0, anchored_at=0)
            db.add(b); db.flush()
            for i, lf in enumerate(man["leaves"]):
                if not db.execute(select(Credential.id).where(Credential.leaf == lf)).first():
                    db.add(Credential(id="ALM-" + lf[2:14].upper(), inst_id=b.inst_id, kind="batch", leaf=lf, batch_id=b.id, leaf_index=i, status="issued", kind_label="Recovered"))
                    rebuilt += 1
        for ev in self.chain.events("CredentialIssued"):
            lf = hx(ev["args"]["hash"])
            if not db.execute(select(Credential.id).where(Credential.leaf == lf)).first():
                inst = db.execute(select(Institution).where(Institution.chain_id == ev["args"]["instId"])).scalar()
                db.add(Credential(id="ALM-" + lf[2:14].upper(), inst_id=inst.id if inst else None, kind="single", leaf=lf, record_cid=ev["args"]["cid"], status="issued", kind_label="Recovered"))
                rebuilt += 1
        db.commit(); self._tree_cache.clear(); return dict(rebuilt_credentials=rebuilt)
