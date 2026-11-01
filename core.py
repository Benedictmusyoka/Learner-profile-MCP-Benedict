"""Shared logic: storage, pattern analysis, wording guardrails, approval.
Learner IDs should be pseudonyms (e.g. 'L-0042'), never names."""
import os, re, json, sqlite3, time

DB = os.environ.get("LP_DB", os.path.join(os.path.dirname(os.path.abspath(__file__)), "learner.db"))
KINDS = {"quiz", "project", "teacher_note"}
ATL = {"", "Thinking", "Research", "Communication", "Social", "Self-management"}
MIN_SOURCES, MIN_TERMS = 3, 2          # evidence floor: tune with teachers

SCHEMA = """
CREATE TABLE IF NOT EXISTS evidence(
  id INTEGER PRIMARY KEY, learner TEXT, term TEXT, subject TEXT, kind TEXT,
  score REAL, atl TEXT, note TEXT, teacher TEXT,
  status TEXT DEFAULT 'pending', created REAL);
CREATE TABLE IF NOT EXISTS proposals(
  id INTEGER PRIMARY KEY, learner TEXT, evidence_ids TEXT, diff TEXT,
  wording TEXT, model TEXT, status TEXT DEFAULT 'pending',
  decided_by TEXT, decided_at REAL, reason TEXT, created REAL);
"""

SCHEMA2 = """
CREATE TABLE IF NOT EXISTS classes(id TEXT PRIMARY KEY, name TEXT, grade TEXT);
CREATE TABLE IF NOT EXISTS teachers(name TEXT PRIMARY KEY, pw_hash TEXT, role TEXT DEFAULT 'teacher', created REAL);
CREATE TABLE IF NOT EXISTS teacher_classes(teacher TEXT, class_id TEXT, PRIMARY KEY(teacher, class_id));
CREATE TABLE IF NOT EXISTS learners(id TEXT PRIMARY KEY, class_id TEXT, display_name TEXT, age_band TEXT DEFAULT '9-12',
  consent_status TEXT DEFAULT 'none', consent_by TEXT, consent_at REAL, created REAL);
CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY, at REAL, actor TEXT, action TEXT, target TEXT, detail TEXT);
"""

def conn():
    c = sqlite3.connect(DB); c.row_factory = sqlite3.Row
    c.executescript(SCHEMA + SCHEMA2)
    try: os.chmod(DB, 0o600)
    except OSError: pass
    return c

def rows(c, learner, statuses):
    q = ",".join("?" * len(statuses))
    return [dict(r) for r in c.execute(
        f"SELECT * FROM evidence WHERE learner=? AND status IN ({q}) ORDER BY term,id",
        (learner, *statuses))]

def _slope(p):
    if len(p) < 2: return 0.0
    mx = sum(x for x, _ in p) / len(p); my = sum(y for _, y in p) / len(p)
    den = sum((x - mx) ** 2 for x, _ in p)
    return sum((x - mx) * (y - my) for x, y in p) / den if den else 0.0

def analyze(rs):
    terms = sorted({r["term"] for r in rs}); idx = {t: i for i, t in enumerate(terms)}
    out = {}
    for s in sorted({r["subject"] for r in rs}):
        es = [r for r in rs if r["subject"] == s]
        sc = [r for r in es if r["score"] is not None]
        by = {}
        for r in sc: by.setdefault(r["term"], []).append(r["score"])
        pts = [(idx[t], sum(v) / len(v)) for t, v in by.items()]
        mean = sum(r["score"] for r in sc) / len(sc) if sc else None
        nt = len({r["term"] for r in es})
        enough = len(es) >= MIN_SOURCES and nt >= MIN_TERMS
        sl = _slope(pts); trend = "" if not enough or len(pts) < 2 else ("rising" if sl > 2 else "falling" if sl < -2 else "steady")
        last2 = sorted({r["term"] for r in sc})[-2:]; rsc = [r["score"] for r in sc if r["term"] in last2]
        recent = sum(rsc) / len(rsc) if rsc else None; reason = ""
        if not enough: level = "not enough evidence yet"
        elif mean is None: level = "observed in notes only"
        elif mean >= 70: level = "emerging strength"
        elif mean < 55: level = "may need support"; reason = "low average"
        else: level = "developing"
        if level == "developing" and trend == "falling" and recent is not None and recent < 60:   # a decline the all-time average would hide
            level = "may need support"; reason = "recent decline"
        item = {"level": level, "trend": trend, "sources": len(es), "terms": nt,
                "average": None if mean is None else round(mean), "recent_average": None if recent is None else round(recent),
                "evidence_ids": [f"E{r['id']}" for r in es]}
        if reason: item["reason"] = reason
        if level == "may need support":
            item["check_first"] = ["attendance in those terms", "language of instruction",
                                   "sight/hearing", "circumstances at home or school"]
        out[s] = item
    return out

def atl_summary(rs):
    d = {}
    for r in rs:
        if r["atl"]: d.setdefault(r["atl"], []).append(f"E{r['id']}")
    return d

BANNED = [r"\bshould (become|be a|study|choose|take|pursue)", r"\bmust\b", r"\bwill (be|become)\b",
          r"\bdestined\b", r"\bnot (suited|cut out)\b", r"\bcannot\b", r"\bbest career\b",
          r"\bideal career\b", r"\byou need to\b", r"\bnever\b", r"\bonly option\b", r"\bgenius\b",
          r"\blow ability\b", r"\bweak learner\b", r"\bslow learner\b"]

def lint_wording(text, valid_ids):
    """Guardrail between any model and the teacher. Returns list of problems."""
    probs = []
    if not text or len(text) > 1200: probs.append("wording must be 1-1200 characters")
    cited = {int(x) for x in re.findall(r"\[E(\d+)\]", text or "")}
    if not cited: probs.append("cite sources like [E12] for every claim")
    bad = cited - valid_ids
    if bad: probs.append("cites unknown evidence: " + ", ".join(f"E{i}" for i in sorted(bad)))
    for p in BANNED:
        m = re.search(p, text or "", re.I)
        if m: probs.append(f"prescriptive/labelling phrase '{m.group(0)}': describe evidence and pose questions instead")
    if "?" not in (text or ""): probs.append("include at least one open question for the learner or family")
    return probs

def diff(before, after):
    d = {}
    for s, a in after.items():
        b = before.get(s)
        if b != a:
            d[s] = {"before": None if not b else {k: b[k] for k in ("level", "sources", "average", "trend")},
                    "after": {k: a[k] for k in ("level", "sources", "average", "trend")}}
    return d

def approve(pid, by, ok=True, reason="", discard_evidence=False):
    """Called ONLY by the teacher CLI. Not exposed as an MCP tool, by design."""
    c = conn()
    p = c.execute("SELECT * FROM proposals WHERE id=?", (pid,)).fetchone()
    if not p or p["status"] != "pending": raise ValueError("no such pending proposal")
    ids = json.loads(p["evidence_ids"])
    with c:
        c.execute("UPDATE proposals SET status=?,decided_by=?,decided_at=?,reason=? WHERE id=?",
                  ("approved" if ok else "rejected", by, time.time(), reason, pid))
        mark = "approved" if ok else ("discarded" if discard_evidence else None)
        if mark:
            c.executemany("UPDATE evidence SET status=? WHERE id=?", [(mark, i) for i in ids])


# ---------- v2: school data, consent, access, privacy ----------
import hashlib, hmac, re as _re
def strict(): return os.environ.get("LP_STRICT") == "1"      # deployment mode: learners must be registered with consent
def audit(c, actor, action, target="", detail=""):
    c.execute("INSERT INTO audit(at,actor,action,target,detail) VALUES(?,?,?,?,?)", (time.time(), actor, action, target, detail))
def hash_pw(pw):
    salt = os.urandom(16); return f"pbkdf2${salt.hex()}${hashlib.pbkdf2_hmac('sha256', pw.encode(), salt, 200_000).hex()}"
def check_pw(pw, stored):
    try:
        _, s, h = stored.split("$"); return hmac.compare_digest(hashlib.pbkdf2_hmac("sha256", pw.encode(), bytes.fromhex(s), 200_000).hex(), h)
    except Exception: return False
_DUMMY = hash_pw("dummy-password-for-timing")
ID_OK = _re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,39}$")
def add_class(cid, name, grade=""):
    if not ID_OK.match(cid): raise ValueError("class id: letters, digits, . _ - only")
    c = conn()
    with c: c.execute("INSERT OR REPLACE INTO classes VALUES(?,?,?)", (cid, name, grade)); audit(c, "admin", "add_class", cid)
def create_teacher(name, pw, role="teacher", classes=()):
    if not name.strip() or ":" in name: raise ValueError("teacher name must be non-empty and contain no colon")
    if role not in ("teacher", "head"): raise ValueError("role must be teacher or head")
    if len(pw) < 10: raise ValueError("password must be at least 10 characters")
    c = conn()
    with c:
        c.execute("INSERT OR REPLACE INTO teachers VALUES(?,?,?,?)", (name.strip(), hash_pw(pw), role, time.time()))
        for k in classes: c.execute("INSERT OR IGNORE INTO teacher_classes VALUES(?,?)", (name.strip(), k))
        audit(c, "admin", "create_teacher", name.strip(), role)
def verify_teacher(name, pw):
    r = conn().execute("SELECT * FROM teachers WHERE name=?", (name,)).fetchone()
    ok = check_pw(pw, r["pw_hash"] if r else _DUMMY)
    return r["role"] if r and ok else None
def add_learner(lid, cid, display_name="", age_band="9-12", actor="admin"):
    if not ID_OK.match(lid): raise ValueError("learner id: letters, digits, . _ - only (use a pseudonym, not a name)")
    if age_band not in ("9-12", "13-15"): raise ValueError("age_band must be 9-12 or 13-15")
    c = conn()
    if not c.execute("SELECT 1 FROM classes WHERE id=?", (cid,)).fetchone(): raise ValueError("unknown class")
    with c: c.execute("INSERT OR REPLACE INTO learners(id,class_id,display_name,age_band,created) VALUES(?,?,?,?,?)", (lid, cid, display_name.strip(), age_band, time.time())); audit(c, actor, "add_learner", lid)
def set_consent(lid, status, by):
    if status not in ("granted", "withdrawn", "none"): raise ValueError("status must be granted, withdrawn or none")
    c = conn()
    if not c.execute("SELECT 1 FROM learners WHERE id=?", (lid,)).fetchone(): raise ValueError("unknown learner")
    with c: c.execute("UPDATE learners SET consent_status=?,consent_by=?,consent_at=? WHERE id=?", (status, by, time.time(), lid)); audit(c, by, "consent_" + status, lid)
def consent_ok(c, lid):
    r = c.execute("SELECT consent_status FROM learners WHERE id=?", (lid,)).fetchone(); return bool(r and r["consent_status"] == "granted")
def can_access(c, teacher, lid):
    t = c.execute("SELECT role FROM teachers WHERE name=?", (teacher,)).fetchone(); l = c.execute("SELECT class_id FROM learners WHERE id=?", (lid,)).fetchone()
    if not t or not l: return False
    return t["role"] == "head" or bool(c.execute("SELECT 1 FROM teacher_classes WHERE teacher=? AND class_id=?", (teacher, l["class_id"])).fetchone())
def can_access_class(c, teacher, cid):
    t = c.execute("SELECT role FROM teachers WHERE name=?", (teacher,)).fetchone()
    if not t or not c.execute("SELECT 1 FROM classes WHERE id=?", (cid,)).fetchone(): return False
    return t["role"] == "head" or bool(c.execute("SELECT 1 FROM teacher_classes WHERE teacher=? AND class_id=?", (teacher, cid)).fetchone())
def export_learner(c, lid):
    l = c.execute("SELECT * FROM learners WHERE id=?", (lid,)).fetchone()
    return {"learner": dict(l) if l else None, "evidence": [dict(r) for r in c.execute("SELECT * FROM evidence WHERE learner=? ORDER BY id", (lid,))],
            "proposals": [dict(r) for r in c.execute("SELECT * FROM proposals WHERE learner=? ORDER BY id", (lid,))]}
def erase_learner(lid, by):
    """Right to erasure: removes the learner, all evidence and proposals. The audit log keeps only that it happened."""
    c = conn()
    if not c.execute("SELECT 1 FROM learners WHERE id=?", (lid,)).fetchone(): raise ValueError("unknown learner")
    with c:
        n = c.execute("DELETE FROM evidence WHERE learner=?", (lid,)).rowcount; m = c.execute("DELETE FROM proposals WHERE learner=?", (lid,)).rowcount
        c.execute("DELETE FROM learners WHERE id=?", (lid,)); audit(c, by, "erase_learner", lid, f"{n} evidence rows, {m} proposals removed")
def class_overview(c, cid):
    out = []
    for l in c.execute("SELECT * FROM learners WHERE class_id=? ORDER BY display_name,id", (cid,)).fetchall():
        a = analyze(rows(c, l["id"], ["approved"]))
        sup = [s for s, v in a.items() if v["level"] == "may need support"]; strong = [s for s, v in a.items() if v["level"] == "emerging strength"]
        pe = c.execute("SELECT COUNT(*) FROM evidence WHERE learner=? AND status='pending'", (l["id"],)).fetchone()[0]
        pp = c.execute("SELECT COUNT(*) FROM proposals WHERE learner=? AND status='pending'", (l["id"],)).fetchone()[0]
        n = c.execute("SELECT COUNT(*) FROM evidence WHERE learner=? AND status='approved'", (l["id"],)).fetchone()[0]
        prio = 0 if sup else 1 if pp else 2 if pe else 3 if strong else 4
        out.append({"id": l["id"], "name": l["display_name"] or l["id"], "consent": l["consent_status"], "approved": n, "support": sup, "strong": strong, "pending_evidence": pe, "pending_proposals": pp, "priority": prio, "enough": any(v["level"] != "not enough evidence yet" for v in a.values())})
    return sorted(out, key=lambda r: (r["priority"], r["name"]))
