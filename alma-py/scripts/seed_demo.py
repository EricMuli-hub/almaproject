"""Fills a running Alma API with a small, realistic demo: two institutions, students, an employer, a regulator,
single and batch records, one revoked record, one consent.   python scripts/seed_demo.py [--api http://localhost:8000]"""
import argparse, sys
import httpx

p = argparse.ArgumentParser(); p.add_argument("--api", default="http://localhost:8000"); p.add_argument("--owner", default="owner@alma.local")
p.add_argument("--owner-password", default="change-me-now-please"); a = p.parse_args()
c = httpx.Client(base_url=a.api, timeout=120)
PW = "demo-password-1"


def call(method, path, token=None, **kw):
    r = c.request(method, path, headers={"Authorization": "Bearer " + token} if token else {}, **kw)
    if r.status_code >= 400 and r.status_code != 409: sys.exit(f"{method} {path} -> {r.status_code} {r.text}")
    return r


def login(email, pw=PW): return call("POST", "/auth/login", json={"email": email, "password": pw}).json()["token"]


owner = login(a.owner, a.owner_password)
for name, mail in [("University of Nairobi", "registrar@uon.demo"), ("Strathmore University", "registrar@strath.demo")]:
    call("POST", "/admin/institutions", owner, json={"name": name, "admin_email": mail, "password": PW})
call("POST", "/admin/regulators", owner, json={"email": "regulator@cue.demo", "name": "Commission for University Education", "password": PW})
e = call("POST", "/auth/employer", json={"email": "hr@safaricom.demo", "name": "Safaricom HR", "password": PW})
if e.status_code == 200: call("POST", f"/admin/employers/{e.json()['id']}/approve", owner)
students = [("amina@students.demo", "Amina Wanjiru"), ("brian@students.demo", "Brian Otieno"), ("cate@students.demo", "Catherine Mwende")]
reg = login("registrar@uon.demo")
for mail, name in students:
    r = call("POST", "/institution/students", reg, json={"email": mail, "name": name})
    if r.status_code == 200: call("POST", "/auth/activate", json={"email": mail, "invite": r.json()["invite_code"], "password": PW})
one = call("POST", "/institution/credentials", reg, json={"holder_email": "amina@students.demo", "label": "Degree certificate", "record": {"award": "BSc Computer Science", "grade": "First Class Honours", "year": 2025, "student_no": "S-1001"}}).json()
bad = call("POST", "/institution/credentials", reg, json={"holder_email": "brian@students.demo", "label": "Diploma", "record": {"award": "Diploma in IT", "grade": "Credit", "year": 2023, "student_no": "S-1002"}}).json()
call("POST", f"/institution/credentials/{bad['credential_id']}/revoke", reg)
items = [{"holder_email": students[i % 3][0], "label": "Transcript", "record": {"unit": f"Unit {i + 1}", "mark": 55 + (i * 7) % 40, "year": 2025}} for i in range(60)]
b = call("POST", "/institution/credentials/batch", reg, json={"items": items}).json()
amina = login("amina@students.demo")
call("POST", f"/student/credentials/{one['credential_id']}/consent", amina, json={"verifier_email": "hr@safaricom.demo", "days": 30, "purpose": "Graduate role application"})
print("Demo ready. All demo passwords: " + PW)
print("  registrar  registrar@uon.demo   (also registrar@strath.demo)")
print("  student    amina@students.demo  (brian@, cate@ too)")
print("  employer   hr@safaricom.demo")
print("  regulator  regulator@cue.demo")
print("  owner      " + a.owner)
print("Try the check page with:", one["credential_id"], "(valid),", bad["credential_id"], "(revoked),", b["credential_ids"][0], "(batch record)")
