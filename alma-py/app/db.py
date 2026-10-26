"""Relational index and operational data. Anything here can be rebuilt from the chain and the
content store, except the per record keys (those are deliberately only here, so deleting one
erases the record for good)."""
import json
from sqlalchemy import (create_engine, Column, Integer, String, Text, Float, Boolean, ForeignKey, Index, LargeBinary, event)
from sqlalchemy.orm import declarative_base, sessionmaker, relationship

Base = declarative_base()


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    email = Column(String(190), unique=True, index=True, nullable=False)
    name = Column(String(190), default="")
    role = Column(String(30), index=True)           # platform_admin, university_admin, student, employer, regulator
    pw = Column(String(300), default="")
    address = Column(String(64), index=True)
    key_enc = Column(LargeBinary)                    # chain key wrapped with the master key
    institution_id = Column(Integer, index=True)     # local institution row id
    status = Column(String(20), default="active")    # active, pending, invited, disabled
    invite = Column(String(64), default="")
    created = Column(Integer)


class Institution(Base):
    __tablename__ = "institutions"
    id = Column(Integer, primary_key=True)
    chain_id = Column(Integer, index=True)
    name = Column(String(190))
    admin_user_id = Column(Integer)
    status = Column(String(20), default="active")    # active, held, suspended
    flagged = Column(Boolean, default=False)


class Batch(Base):
    __tablename__ = "batches"
    id = Column(Integer, primary_key=True)
    root = Column(String(70), unique=True, index=True)
    inst_id = Column(Integer, index=True)
    count = Column(Integer)
    manifest_cid = Column(String(80))
    tx_hash = Column(String(80))
    gas = Column(Integer)
    anchored_at = Column(Integer)


class Credential(Base):
    __tablename__ = "credentials"
    id = Column(String(40), primary_key=True)        # public credential id
    inst_id = Column(Integer, index=True)
    holder_id = Column(Integer, index=True)
    kind = Column(String(10))                        # single, batch
    leaf = Column(String(70), index=True)
    batch_id = Column(Integer, index=True)
    leaf_index = Column(Integer)
    record_cid = Column(String(80))
    status = Column(String(12), default="queued", index=True)   # queued, issued, revoked, erased
    kind_label = Column(String(60), default="")      # e.g. "Transcript" (not personal)
    queued_blob = Column(LargeBinary)                # encrypted record waiting for the next batch
    issued_at = Column(Integer)


class KeyVault(Base):
    __tablename__ = "key_vault"
    credential_id = Column(String(40), primary_key=True)
    dek_enc = Column(LargeBinary)
    created = Column(Integer)


class LedgerEvent(Base):
    __tablename__ = "ledger_events"
    id = Column(Integer, primary_key=True)
    ts = Column(Integer, index=True)
    actor = Column(String(64), index=True)
    inst_id = Column(Integer, index=True)
    name = Column(String(40))
    success = Column(Boolean, default=True)
    size = Column(Integer, default=1)
    error = Column(String(200), default="")
    tx_hash = Column(String(80), default="")
    gas = Column(Integer, default=0)
    entropy = Column(Float, default=0.0)
    source = Column(String(10), default="api")      # api (our server saw it) or ledger (found by the watcher)
    __table_args__ = (Index("ix_actor_ts", "actor", "ts"),)


class Anomaly(Base):
    __tablename__ = "anomalies"
    id = Column(Integer, primary_key=True)
    ts = Column(Integer, index=True)
    actor = Column(String(64))
    inst_id = Column(Integer)
    score = Column(Float)
    severity = Column(String(10))
    reasons = Column(Text)
    action = Column(String(120), default="")
    status = Column(String(12), default="open")      # open, confirmed, dismissed


class Consent(Base):
    __tablename__ = "consents"
    id = Column(Integer, primary_key=True)
    credential_id = Column(String(40), index=True)
    verifier_id = Column(Integer, index=True)
    purpose = Column(String(200))
    granted = Column(Integer)
    until = Column(Integer)
    revoked = Column(Integer, default=0)
    tx_hash = Column(String(80), default="")


class AuditLog(Base):
    __tablename__ = "audit_log"
    id = Column(Integer, primary_key=True)
    ts = Column(Integer)
    actor = Column(String(190))
    action = Column(String(80))
    detail = Column(Text)
    prev = Column(String(70))
    hash = Column(String(70))


def make_engine(url):
    kw = {}
    if url.startswith("sqlite"):
        kw = {"connect_args": {"check_same_thread": False}}
    else:
        kw = {"pool_size": 20, "max_overflow": 40, "pool_pre_ping": True}
    eng = create_engine(url, **kw)
    if url.startswith("sqlite"):
        @event.listens_for(eng, "connect")
        def _p(dbapi, _):
            c = dbapi.cursor(); c.execute("PRAGMA journal_mode=WAL"); c.execute("PRAGMA synchronous=NORMAL"); c.close()
    Base.metadata.create_all(eng)
    return eng, sessionmaker(eng, expire_on_commit=False)
