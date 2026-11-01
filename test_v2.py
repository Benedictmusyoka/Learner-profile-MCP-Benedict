"""v2 tests: consent, access control, CSV import, overview, approvals scoping, privacy, XSS, CSRF, draft button."""
import base64, json, os, re, sys, tempfile
os.environ.update(LP_DB=tempfile.mktemp(suffix=".db"), LP_AGENT_TOKEN="agent-token-0123456789", DRAFTER="stub")
os.environ.pop("LP_STRICT", None)
import core, http_server, server
from starlette.testclient import TestClient
cl = TestClient(http_server.app); PW = "teacher-pass-123"
core.add_class("CA", "Class A"); core.add_class("CB", "Class B")
core.create_teacher("Ms A", PW, "teacher", ["CA"]); core.create_teacher("Mr B", PW, "teacher", ["CB"]); core.create_teacher("Head", PW, "head")
core.add_learner("LA1", "CA", "<script>alert(1)</script>"); core.add_learner("LB1", "CB", "Bea B."); core.add_learner("LA2", "CA", "Cleo C.")
core.set_consent("LA1", "granted", "Ms A"); core.set_consent("LB1", "granted", "Mr B")
H = lambda u, p=PW: {"Authorization": "Basic " + base64.b64encode(f"{u}:{p}".encode()).decode()}
R = []
def t(name, ok, detail=""): R.append(ok); print(("PASS " if ok else "FAIL ") + name + (f"  [{detail}]" if detail and not ok else ""))
tokof = lambda html: re.search(r'name="t" value="(\w+)"', html).group(1)
tokfor = lambda html, action: re.search(r'action="' + re.escape(action) + r'"[^>]*><input type="hidden" name="t" value="(\w+)"', html).group(1)

e = server.add_evidence("LA2", "T1", "Maths", "quiz", "Ms A", 70)       # registered, no consent
t("strict mode: no consent -> evidence refused", "error" in e and "consent" in e["error"], e)
os.environ["LP_STRICT"] = "1"
e1 = server.add_evidence("ZZZ", "T1", "Maths", "quiz", "Ms A", 70); e2 = server.add_evidence("LA2", "T1", "Maths", "quiz", "Ms A", 70); e3 = server.add_evidence("LA1", "T1", "Maths", "quiz", "Ms A", 70)
t("strict mode: unregistered and no-consent refused; consented accepted", "error" in e1 and "error" in e2 and e3.get("status") == "pending", (e1, e2, e3))
core.set_consent("LA1", "withdrawn", "Ms A"); e4 = server.add_evidence("LA1", "T2", "Maths", "quiz", "Ms A", 70); core.set_consent("LA1", "granted", "Ms A")
t("withdrawn consent blocks new evidence", "error" in e4, e4)
t("passwords stored hashed, never in plain text", PW not in json.dumps([dict(r) for r in core.conn().execute("SELECT * FROM teachers")]))
t("no login / wrong password / unknown user -> 401", [cl.get("/classes").status_code, cl.get("/classes", headers=H("Ms A", "nope")).status_code, cl.get("/classes", headers=H("Nobody")).status_code] == [401] * 3)
t("teacher sees own class, not another's", cl.get("/class/CA", headers=H("Ms A")).status_code == 200 and cl.get("/class/CB", headers=H("Ms A")).status_code == 404)
t("teacher cannot open another class's learner (404, no existence leak)", cl.get("/learner/LB1", headers=H("Ms A")).status_code == 404 and cl.get("/learner/LB1/export.json", headers=H("Ms A")).status_code == 404 and cl.get("/learner/LB1/sheet", headers=H("Ms A")).status_code == 404)
t("head role sees every class", cl.get("/learner/LB1", headers=H("Head")).status_code == 200)
page = cl.get("/learner/LA1", headers=H("Ms A")).text
t("learner names are HTML-escaped (XSS)", "<script>alert(1)</script>" not in page and "&lt;script&gt;" in page)
r = cl.post("/learner/LA1/evidence", headers=H("Ms A"), data={"t": "forged", "term": "T2", "subject": "Maths", "kind": "quiz", "score": "70"}); t("forged CSRF token on evidence form -> 403", r.status_code == 403)
r = cl.post("/learner/LA1/evidence", headers=H("Ms A"), data={"t": tokfor(page, "/learner/LA1/evidence"), "term": "T2", "subject": "Maths", "kind": "quiz", "score": "75", "note": "ok"}, follow_redirects=False)
t("evidence form stores a pending entry under the logged-in teacher", r.status_code == 303 and core.conn().execute("SELECT teacher,status FROM evidence WHERE term='T2' AND learner='LA1'").fetchone()[:] == ("Ms A", "pending"))
cp = cl.get("/class/CA", headers=H("Ms A")).text
csv = "learner_id,term,subject,kind,score,note\nLA1,T3,Maths,quiz,80,fine\nLB1,T3,Maths,quiz,80,wrong class\nLA1,T3,Maths,quiz,abc,bad score\nLA1,T3,Maths,quiz,200,out of range\nLA2,T3,Maths,quiz,60,no consent\n"
r = cl.post("/class/CA/import", headers=H("Ms A"), data={"t": tokof(cp), "csv": csv}, follow_redirects=False)
m = re.search(r"msg=(.*)", r.headers["location"]).group(1); n = core.conn().execute("SELECT COUNT(*) FROM evidence WHERE term='T3'").fetchone()[0]
t("CSV import: 1 row accepted, 4 rejected (wrong class, bad score, range, no consent)", n == 1 and "Imported%201" in m and "4%20rejected" in m, (n, m))
# overview ordering: support first
c = core.conn(); core.add_learner("LA3", "CA", "Dee D."); core.set_consent("LA3", "granted", "Ms A")
for tm, s in [("T1", 45), ("T2", 50), ("T3", 48)]: c.execute("INSERT INTO evidence(learner,term,subject,kind,score,teacher,status,created) VALUES('LA3',?,?,?,?,?,?,0)", (tm, "English", "quiz", s, "Ms A", "approved"))
for tm, s in [("T1", 80), ("T2", 85), ("T3", 90)]: c.execute("INSERT INTO evidence(learner,term,subject,kind,score,teacher,status,created) VALUES('LA2',?,?,?,?,?,?,0)", (tm, "Mathematics", "quiz", s, "Ms A", "approved"))
c.commit(); ov = core.class_overview(c, "CA")
t("class overview puts 'worth a check-in' first and flags strengths", ov[0]["id"] == "LA3" and ov[0]["support"] == ["English"] and "Mathematics" in [x for r in ov for x in r["strong"]], [(r["id"], r["priority"]) for r in ov])
sheet = cl.get("/learner/LA3/sheet", headers=H("Ms A")).text
t("conversation sheet: disclaimer, context checks, no verdict language", "not a verdict" in sheet and "attendance" in sheet and "should become" not in sheet)
ids = [r["id"] for r in core.rows(core.conn(), "LA1", ["pending"])]
w = "Results are recorded " + " ".join(f"[E{i}]" for i in ids) + ". What does the learner enjoy most about this subject?"
pr = server.propose_update("LA1", w, "demo draft"); pid = pr["proposal_id"]
ap = cl.get("/teacher", headers=H("Ms A")).text; bp = cl.get("/teacher", headers=H("Mr B")).text
t("approvals page: shows proposal to its own teacher only", f"Proposal #{pid}" in ap and f"Proposal #{pid}" not in bp)
r = cl.post("/teacher/decide", headers=H("Mr B"), data={"id": pid, "t": tok if False else __import__("web").tok("Mr B", f"decide:{pid}"), "action": "approve"}); t("another class's teacher cannot approve (404)", r.status_code == 404)
r = cl.post("/teacher/decide", headers=H("Ms A"), data={"id": pid, "t": "forged", "action": "approve"}); t("forged CSRF token on approval -> 403", r.status_code == 403)
r = cl.post("/teacher/decide", headers=H("Ms A"), data={"id": pid, "t": tokof(ap), "action": "approve"}, follow_redirects=False)
row = core.conn().execute("SELECT decided_by,status FROM proposals WHERE id=?", (pid,)).fetchone()
t("assigned teacher approves; decision recorded under their name", r.status_code == 303 and tuple(row) == ("Ms A", "approved"))
server.add_evidence("LA1", "T4", "Maths", "quiz", "Ms A", 77); page = cl.get("/learner/LA1", headers=H("Ms A")).text
r = cl.post("/learner/LA1/draft", headers=H("Ms A"), data={"t": tokfor(page, "/learner/LA1/draft")}, follow_redirects=False)
pp = core.conn().execute("SELECT model,status FROM proposals WHERE learner='LA1' AND status='pending'").fetchall()
t("draft button runs the real agent and queues exactly one pending proposal", r.status_code == 303 and len(pp) == 1 and pp[0]["model"] == "stub", (r.status_code, [tuple(x) for x in pp], r.headers.get("location")))
r = cl.post("/learner/LA1/draft", headers=H("Ms A"), data={"t": "forged"}); t("forged CSRF token on draft button -> 403", r.status_code == 403)
exp = core.export_learner(core.conn(), "LA3"); t("export contains the learner's evidence", exp["learner"]["id"] == "LA3" and len(exp["evidence"]) == 3)
core.erase_learner("LA3", "Head"); c = core.conn()
left = c.execute("SELECT (SELECT COUNT(*) FROM evidence WHERE learner='LA3')+(SELECT COUNT(*) FROM proposals WHERE learner='LA3')+(SELECT COUNT(*) FROM learners WHERE id='LA3')").fetchone()[0]
au = c.execute("SELECT detail FROM audit WHERE action='erase_learner'").fetchone()
t("erasure removes learner, evidence and proposals; audit keeps only the fact", left == 0 and au and "3 evidence rows" in au[0])
t("audit log records views and exports", c.execute("SELECT COUNT(*) FROM audit WHERE action IN ('view_learner','export_learner','view_sheet')").fetchone()[0] >= 3)
def lv(scores, subj="English"):
    d = core.analyze([{"id": i + 1, "term": f"T{i+1}", "subject": subj, "score": sc, "kind": "quiz", "atl": "", "note": ""} for i, sc in enumerate(scores)]); return d[subj]
fall = lv([68, 63, 58, 54, 50, 46]); rise = lv([40, 50, 60, 70]); flat = lv([60, 61, 59, 60])
t("analysis: a decline the average hides is flagged (68 to 46 over 6 terms)", fall["level"] == "may need support" and fall.get("reason") == "recent decline" and "check_first" in fall, fall)
t("analysis: a learner improving from a low start is not flagged", rise["level"] == "developing" and rise["trend"] == "rising", rise)
t("analysis: a steady mid learner is not flagged", flat["level"] == "developing", flat)
multi = core.analyze([{"id": i, "term": f"T{i%3+1}", "subject": s, "score": 70 + i, "kind": "quiz", "atl": "", "note": ""} for i, s in enumerate(["Maths", "English", "Science"] * 3)])
t("analysis: several subjects in one learner analyse independently", sorted(multi) == ["English", "Maths", "Science"] and all(v["sources"] == 3 for v in multi.values()), multi)
print(f"\n{sum(R)}/{len(R)} passed"); sys.exit(0 if all(R) else 1)
