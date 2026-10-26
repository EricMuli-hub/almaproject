"""REST API. Stateless: run as many copies as needed behind a load balancer."""
import os, time, json, pathlib
import jwt
from fastapi import FastAPI, Depends, HTTPException, Header, Request
from fastapi.responses import JSONResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sqlalchemy import select

from .core import Settings, ROOT
from .service import App, Denied
from .db import User, Anomaly, Institution, LedgerEvent, Credential, Batch, Consent
from .ai import evaluate


class Login(BaseModel): email: str; password: str
class EmployerIn(BaseModel): email: str; name: str; password: str = Field(min_length=8)
class InstIn(BaseModel): name: str; admin_email: str; password: str = Field(min_length=8)
class RegIn(BaseModel): email: str; name: str; password: str = Field(min_length=8)
class StudentIn(BaseModel): email: str; name: str
class ActivateIn(BaseModel): email: str; invite: str; password: str = Field(min_length=8)
class IssueIn(BaseModel): holder_email: str; record: dict; label: str = "Record"
class BatchIn(BaseModel): items: list[IssueIn]
class ConsentIn(BaseModel): verifier_email: str; days: float = 30; purpose: str = "employment check"
class StatusIn(BaseModel): active: bool; reason: str = ""
class PackageIn(BaseModel): record: dict; salt: str; proof: list | None = None; root: str | None = None


def create_app(settings: Settings | None = None, admin_email="owner@alma.local", admin_password="") -> FastAPI:
    core = App(settings)
    app = FastAPI(title="Alma credential verification API", version="1.0")
    app.state.core = core
    with core.Session() as db:
        core.ensure_platform_admin(db, admin_email, admin_password or os.getenv("ADMIN_PASSWORD", "change-me-now-please"))

    @app.exception_handler(Denied)
    async def denied(_, e: Denied): return JSONResponse({"detail": str(e)}, status_code=e.code)

    def db_dep():
        with core.Session() as db: yield db

    def user_dep(authorization: str = Header(default=""), db=Depends(db_dep)) -> User:
        try: claims = jwt.decode(authorization.removeprefix("Bearer ").strip(), core.s.jwt, algorithms=["HS256"])
        except Exception: raise HTTPException(401, "sign in first")
        u = db.get(User, claims["sub"])
        if not u or u.status != "active": raise HTTPException(401, "account not active")
        return u

    def need(*roles):
        def dep(u: User = Depends(user_dep)):
            if u.role not in roles: raise HTTPException(403, f"this needs one of: {', '.join(roles)}")
            return u
        return dep

    # ---- auth ----
    @app.post("/auth/login")
    def login(b: Login, db=Depends(db_dep)):
        u = core.login(db, b.email, b.password)
        tok = jwt.encode({"sub": u.id, "role": u.role, "exp": int(time.time()) + 8 * 3600}, core.s.jwt, algorithm="HS256")
        return {"token": tok, "role": u.role, "name": u.name}

    @app.post("/auth/employer")
    def employer(b: EmployerIn, db=Depends(db_dep)):
        u = core.register_employer(db, b.email, b.name, b.password); return {"id": u.id, "status": u.status}

    @app.post("/auth/activate")
    def activate(b: ActivateIn, db=Depends(db_dep)):
        u = core.activate(db, b.email, b.invite, b.password); return {"status": u.status}

    @app.get("/me")
    def me(u: User = Depends(user_dep)): return {"id": u.id, "email": u.email, "name": u.name, "role": u.role, "chain_address": u.address}

    # ---- platform owner ----
    @app.post("/admin/institutions")
    def inst(b: InstIn, u=Depends(need("platform_admin")), db=Depends(db_dep)):
        i = core.create_institution(db, u, b.name, b.admin_email, b.password); return {"id": i.id, "chain_id": i.chain_id, "name": i.name}

    @app.post("/admin/regulators")
    def reg(b: RegIn, u=Depends(need("platform_admin")), db=Depends(db_dep)):
        r = core.create_regulator(db, u, b.email, b.name, b.password); return {"id": r.id}

    @app.post("/admin/employers/{eid}/approve")
    def approve(eid: int, u=Depends(need("platform_admin")), db=Depends(db_dep)):
        e = core.approve_employer(db, u, eid); return {"id": e.id, "status": e.status}

    @app.get("/admin/employers/pending")
    def pending(u=Depends(need("platform_admin")), db=Depends(db_dep)):
        return [{"id": e.id, "email": e.email, "name": e.name} for e in db.execute(select(User).where(User.role == "employer", User.status == "pending")).scalars()]

    # ---- institution ----
    @app.post("/institution/students")
    def add_student(b: StudentIn, u=Depends(need("university_admin")), db=Depends(db_dep)):
        s = core.add_student(db, u, b.email, b.name); return {"id": s.id, "invite_code": s.invite}

    @app.post("/institution/credentials")
    def issue(b: IssueIn, u=Depends(need("university_admin")), db=Depends(db_dep)): return core.issue_single(db, u, b.holder_email, b.record, b.label)

    @app.post("/institution/credentials/batch")
    def issue_batch(b: BatchIn, u=Depends(need("university_admin")), db=Depends(db_dep)): return core.issue_batch(db, u, [i.model_dump() for i in b.items])

    @app.post("/institution/credentials/queue")
    def queue(b: IssueIn, u=Depends(need("university_admin")), db=Depends(db_dep)): return core.queue(db, u, b.holder_email, b.record, b.label)

    @app.post("/institution/queue/flush")
    def flush(u=Depends(need("university_admin")), db=Depends(db_dep)): return {"anchors": core.flush(db, u)}

    @app.post("/institution/credentials/{cid}/revoke")
    def revoke(cid: str, u=Depends(need("university_admin")), db=Depends(db_dep)): return core.revoke(db, u, cid)

    # ---- student ----
    @app.get("/student/credentials")
    def my_creds(u=Depends(need("student")), db=Depends(db_dep)):
        from .db import Credential
        return [{"id": c.id, "type": c.kind_label, "status": c.status, "issued_at": c.issued_at} for c in db.execute(select(Credential).where(Credential.holder_id == u.id)).scalars()]

    @app.get("/student/credentials/{cid}/package")
    def package(cid: str, u=Depends(need("student")), db=Depends(db_dep)): return core.package_for(db, u, cid)

    @app.post("/student/credentials/{cid}/consent")
    def consent(cid: str, b: ConsentIn, u=Depends(need("student")), db=Depends(db_dep)): return core.grant(db, u, cid, b.verifier_email, b.days, b.purpose)

    @app.delete("/student/credentials/{cid}/consent/{verifier_email}")
    def unconsent(cid: str, verifier_email: str, u=Depends(need("student")), db=Depends(db_dep)): return core.revoke_consent(db, u, cid, verifier_email)

    @app.get("/student/export")
    def export(u=Depends(need("student")), db=Depends(db_dep)): return core.export_student(db, u)

    @app.delete("/student/credentials/{cid}")
    def erase(cid: str, u=Depends(need("student")), db=Depends(db_dep)): return core.erase(db, u, cid)

    # ---- verification ----
    @app.get("/verify/{cid}")
    def verify(cid: str, db=Depends(db_dep)): return core.verify(db, cid)

    @app.post("/verify/package")
    def verify_pkg(b: PackageIn): return core.verify_package(b.model_dump())

    @app.get("/employer/credentials/{cid}")
    def disclose(cid: str, u=Depends(need("employer")), db=Depends(db_dep)): return core.disclose(db, u, cid)

    # ---- regulator ----
    @app.get("/regulator/anomalies")
    def anomalies(u=Depends(need("regulator", "platform_admin")), db=Depends(db_dep)):
        return [dict(id=a.id, ts=a.ts, actor=a.actor, institution=a.inst_id, score=a.score, severity=a.severity, reasons=a.reasons, action=a.action, status=a.status)
                for a in db.execute(select(Anomaly).order_by(Anomaly.id.desc()).limit(200)).scalars()]

    @app.post("/regulator/anomalies/{aid}/{decision}")
    def decide(aid: int, decision: str, u=Depends(need("regulator", "platform_admin")), db=Depends(db_dep)):
        if decision not in ("confirmed", "dismissed"): raise HTTPException(400, "use confirmed or dismissed")
        a = db.get(Anomaly, aid)
        if not a: raise HTTPException(404)
        a.status = decision; core.audit(db, u.email, "anomaly_" + decision, str(aid)); db.commit(); return {"id": aid, "status": decision}

    @app.post("/regulator/institutions/{iid}/status")
    def inst_status(iid: int, b: StatusIn, u=Depends(need("regulator", "platform_admin")), db=Depends(db_dep)): return core.set_institution_status(db, u, iid, b.active, b.reason)

    @app.get("/regulator/stats")
    def stats(u=Depends(need("regulator", "platform_admin")), db=Depends(db_dep)): return core.stats(db)

    @app.get("/regulator/ai/evaluation")
    def ai_eval(u=Depends(need("regulator", "platform_admin"))): return evaluate()

    # ---- system ----
    @app.get("/system/health")
    def health(): return {"ok": True, "chain": "test" if core.chain.tester else "rpc", "contract": core.chain.address, "store": core.store.kind}

    @app.get("/system/audit/verify")
    def audit(u=Depends(need("regulator", "platform_admin")), db=Depends(db_dep)): return core.verify_audit_chain(db)

    @app.get("/system/privacy/chain-check")
    def privacy(u=Depends(need("regulator", "platform_admin")), db=Depends(db_dep)): return core.pii_on_chain_check(db)

    @app.post("/system/recover")
    def recover(u=Depends(need("platform_admin")), db=Depends(db_dep)): return core.recover_index(db)

    # ---- extra read endpoints used by the web interface ----
    @app.get("/institution/overview")
    def inst_overview(u=Depends(need("university_admin")), db=Depends(db_dep)):
        from sqlalchemy import func
        i = db.get(Institution, u.institution_id)
        cnt = lambda st: db.execute(select(func.count(Credential.id)).where(Credential.inst_id == i.id, Credential.status == st)).scalar()
        anchors = db.execute(select(Batch).where(Batch.inst_id == i.id).order_by(Batch.id.desc()).limit(5)).scalars().all()
        return dict(name=i.name, status=i.status, chain_id=i.chain_id, issued=cnt("issued"), queued=cnt("queued"), revoked=cnt("revoked"), erased=cnt("erased"),
                    students=db.execute(select(func.count(User.id)).where(User.institution_id == i.id, User.role == "student")).scalar(),
                    batches=db.execute(select(func.count(Batch.id)).where(Batch.inst_id == i.id)).scalar(),
                    recent_anchors=[dict(root=b.root, count=b.count, gas=b.gas, tx=b.tx_hash, at=b.anchored_at) for b in anchors])

    @app.get("/institution/records")
    def inst_records(limit: int = 300, u=Depends(need("university_admin")), db=Depends(db_dep)):
        rows = db.execute(select(Credential, User).join(User, User.id == Credential.holder_id, isouter=True).where(Credential.inst_id == u.institution_id)
                          .order_by(Credential.issued_at.desc().nullslast()).limit(min(limit, 1000))).all()
        return [dict(id=c.id, type=c.kind_label, status=c.status, kind=c.kind, issued_at=c.issued_at, holder=(h.email if h else None), leaf=c.leaf) for c, h in rows]

    @app.get("/institution/students")
    def inst_students(u=Depends(need("university_admin")), db=Depends(db_dep)):
        return [dict(id=s.id, email=s.email, name=s.name, status=s.status, invite_code=s.invite or None)
                for s in db.execute(select(User).where(User.institution_id == u.institution_id, User.role == "student").order_by(User.id.desc())).scalars()]

    @app.get("/institution/anchors")
    def inst_anchors(u=Depends(need("university_admin")), db=Depends(db_dep)):
        return [dict(root=b.root, count=b.count, gas=b.gas, gas_per_record=round((b.gas or 0) / max(1, b.count), 1), tx=b.tx_hash, cid=b.manifest_cid, at=b.anchored_at)
                for b in db.execute(select(Batch).where(Batch.inst_id == u.institution_id).order_by(Batch.id.desc()).limit(200)).scalars()]

    @app.get("/admin/overview")
    def admin_overview(u=Depends(need("platform_admin")), db=Depends(db_dep)):
        emails = {x.id: x.email for x in db.execute(select(User)).scalars()}
        return dict(institutions=[dict(id=i.id, chain_id=i.chain_id, name=i.name, status=i.status, admin=emails.get(i.admin_user_id)) for i in db.execute(select(Institution)).scalars()],
                    regulators=[dict(id=x.id, email=x.email, name=x.name) for x in db.execute(select(User).where(User.role == "regulator")).scalars()],
                    employers=[dict(id=x.id, email=x.email, name=x.name, status=x.status) for x in db.execute(select(User).where(User.role == "employer")).scalars()])

    @app.get("/regulator/events")
    def events(limit: int = 100, u=Depends(need("regulator", "platform_admin")), db=Depends(db_dep)):
        return [dict(id=e.id, ts=e.ts, actor=e.actor, institution=e.inst_id, name=e.name, success=e.success, size=e.size, gas=e.gas, error=e.error, source=getattr(e, "source", "api"))
                for e in db.execute(select(LedgerEvent).order_by(LedgerEvent.id.desc()).limit(min(limit, 500))).scalars()]

    @app.get("/regulator/ai/experiment")
    def experiment(hard: int = 0, u=Depends(need("regulator", "platform_admin"))):
        from . import dataset
        return dataset.evaluate(seed=42, hard=bool(hard))

    @app.get("/student/consents")
    def my_consents(u=Depends(need("student")), db=Depends(db_dep)):
        rows = db.execute(select(Consent, User).join(User, User.id == Consent.verifier_id).join(Credential, Credential.id == Consent.credential_id).where(Credential.holder_id == u.id).order_by(Consent.id.desc())).all()
        return [dict(id=c.id, credential_id=c.credential_id, verifier=v.email, purpose=c.purpose, granted=c.granted, until=c.until, revoked=bool(c.revoked)) for c, v in rows]

    @app.get("/me/rbac-probe")
    def rbac_probe(u: User = Depends(user_dep)):
        """Asks the contract, without sending anything, what it would let this account do. The refusal text is the contract's own."""
        from eth_account import Account
        d = Account.create().address; h = b"\x01" * 32
        tests = [("registerInstitution", "PlatformAdmin", (d, "probe")), ("registerEmployer", "PlatformAdmin", (d,)), ("registerRegulator", "PlatformAdmin", (d,)),
                 ("registerStudent", "UniversityAdmin", (d,)), ("issueCredential", "UniversityAdmin", (h, d, "cid")), ("anchorBatch", "UniversityAdmin", (h, 1, "cid")),
                 ("revokeCredential", "UniversityAdmin", (h,)), ("setInstitutionStatus", "Regulator or PlatformAdmin", (1, True, False, "probe")),
                 ("grantAccess", "Student", (h, d, 2 ** 40)), ("revokeAccess", "Student", (h, d))]
        out = []
        for fn, needs, args in tests:
            try:
                getattr(core.chain.c.functions, fn)(*args).estimate_gas({"from": u.address}); allowed, msg = True, "the contract accepts the call"
            except Exception as e:
                msg = core.chain._decode(e); allowed = not msg.startswith("NotAllowed")
                if allowed: msg = "role accepted; the contract would then check the details (" + msg.split("(")[0][:40] + ")"
            out.append(dict(action=fn, needs=needs, allowed=allowed, contract_says=msg))
        return dict(address=u.address, role_on_chain=core.chain.role_of(u.address), checks=out)

    @app.get("/system/benchmark")
    def benchmark():
        p = ROOT / "docs" / "BENCHMARK_testchain.json"
        if not p.exists(): raise HTTPException(404, "no benchmark file yet; run scripts/benchmark.py")
        return json.loads(p.read_text())

    @app.get("/system/chain")
    def chain_info():
        return dict(tester=core.chain.tester, rpc_url=core.s.rpc_url or "", address=core.chain.address, abi=core.chain.abi, block=core.chain.w3.eth.block_number, chain_id=core.chain.w3.eth.chain_id)

    @app.get("/system/chain/role/{addr}")
    def chain_role(addr: str):
        try: return {"address": addr, "role": core.chain.role_of(addr)}
        except Exception: raise HTTPException(400, "not an address")

    @app.get("/system/chain/batch/{root}")
    def chain_batch(root: str): return core.chain.batch_status(root)

    app.add_middleware(CORSMiddleware, allow_origins=os.getenv("ALMA_CORS", "*").split(","), allow_methods=["*"], allow_headers=["*"])
    web = pathlib.Path(os.getenv("ALMA_WEB", str(ROOT / "frontend" / "dist")))
    if (web / "index.html").exists():
        app.mount("/assets", StaticFiles(directory=web / "assets"), name="assets")

        @app.get("/", include_in_schema=False)
        def index(): return FileResponse(web / "index.html")

        @app.get("/{path:path}", include_in_schema=False)
        def static_files(path: str):
            f = web / path
            if path and f.is_file() and web in f.resolve().parents: return FileResponse(f)
            raise HTTPException(404)

    return app
