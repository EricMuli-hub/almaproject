"""Runs the same flow against a real JSON-RPC node (Hardhat, Anvil, Ganache, a testnet).
Skipped unless CHAIN_RPC_TEST and FUNDER_KEY_TEST are set."""
import os, shutil, pytest
from fastapi.testclient import TestClient
from app.core import Settings
from app.api import create_app
from tests.conftest import _BASE, login

RPC, KEY = os.getenv("CHAIN_RPC_TEST"), os.getenv("FUNDER_KEY_TEST")
pytestmark = pytest.mark.skipif(not (RPC and KEY), reason="no RPC node configured")


def test_full_flow_on_real_rpc_node(tmp_path):
    shutil.copy(_BASE / "ai_model.joblib", tmp_path / "ai_model.joblib")
    app = create_app(Settings(data_dir=str(tmp_path), rpc_url=RPC, funder_key=KEY), admin_email="owner@alma.test", admin_password="owner-password-1")
    c = TestClient(app); assert c.get("/system/health").json()["chain"] == "rpc"
    own = login(c, "owner@alma.test", "owner-password-1")
    assert c.post("/admin/institutions", json={"name": "Uni R", "admin_email": "r@uni.test", "password": "password-123"}, headers=own).status_code == 200
    adm = login(c, "r@uni.test", "password-123")
    inv = c.post("/institution/students", json={"email": "s@m.test", "name": "S T"}, headers=adm).json()["invite_code"]
    c.post("/auth/activate", json={"email": "s@m.test", "invite": inv, "password": "password-123"})
    one = c.post("/institution/credentials", json={"holder_email": "s@m.test", "record": {"a": 1}}, headers=adm).json()
    b = c.post("/institution/credentials/batch", json={"items": [{"holder_email": "s@m.test", "record": {"n": i}} for i in range(100)]}, headers=adm).json()
    assert c.get(f"/verify/{one['credential_id']}").json()["valid"]
    assert all(c.get(f"/verify/{i}").json()["valid"] for i in b["credential_ids"][:10])
    assert b["anchors"][0]["gas_per_record"] < one["gas"] / 20
