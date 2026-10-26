import shutil, tempfile, pathlib, pytest
from fastapi.testclient import TestClient
from app.core import Settings
from app.api import create_app
from app.ai import Monitor

_BASE = pathlib.Path(tempfile.mkdtemp())
Monitor(_BASE)   # train once, reuse the model file in every test


@pytest.fixture()
def api(tmp_path):
    shutil.copy(_BASE / "ai_model.joblib", tmp_path / "ai_model.joblib")
    app = create_app(Settings(data_dir=str(tmp_path)), admin_email="owner@alma.test", admin_password="owner-password-1")
    c = TestClient(app); c.core = app.state.core
    return c


def login(c, email, pw):
    r = c.post("/auth/login", json={"email": email, "password": pw}); assert r.status_code == 200, r.text
    return {"Authorization": "Bearer " + r.json()["token"]}


@pytest.fixture()
def world(api):
    c = api; h = {}
    h["owner"] = login(c, "owner@alma.test", "owner-password-1")
    for n in ("A", "B"):
        r = c.post("/admin/institutions", json={"name": f"University {n}", "admin_email": f"admin{n}@uni.test", "password": "password-123"}, headers=h["owner"]); assert r.status_code == 200, r.text
        h["admin" + n] = login(c, f"admin{n}@uni.test", "password-123")
    assert c.post("/admin/regulators", json={"email": "reg@kenya.test", "name": "Regulator", "password": "password-123"}, headers=h["owner"]).status_code == 200
    h["reg"] = login(c, "reg@kenya.test", "password-123")
    eid = c.post("/auth/employer", json={"email": "hr@firm.test", "name": "Firm HR", "password": "password-123"}).json()["id"]
    assert c.post(f"/admin/employers/{eid}/approve", headers=h["owner"]).status_code == 200
    h["emp"] = login(c, "hr@firm.test", "password-123")
    for em, name in (("amina@mail.test", "Amina Wanjiru"), ("brian@mail.test", "Brian Otieno")):
        r = c.post("/institution/students", json={"email": em, "name": name}, headers=h["adminA"]); assert r.status_code == 200, r.text
        assert c.post("/auth/activate", json={"email": em, "invite": r.json()["invite_code"], "password": "password-123"}).status_code == 200
        h[em.split("@")[0]] = login(c, em, "password-123")
    return c, h
