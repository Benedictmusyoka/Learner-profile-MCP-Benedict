"""Loads a FICTIONAL demo school: 2 classes, 3 teachers, 16 learners, six terms of marks. Safe to re-run (resets the database file it points at).
Demo logins use the password in LP_DEMO_PASSWORD (default 'demo-pass-1234'). Never use it for real data."""
import os, random, sys
import core
if os.path.exists(core.DB): os.remove(core.DB)
PW = os.environ.get("LP_DEMO_PASSWORD", "demo-pass-1234"); random.seed(26)
core.add_class("C-6B", "Grade 6 Blue", "6"); core.add_class("C-5G", "Grade 5 Green", "5")
core.create_teacher("Ms Wanjiru", PW, "teacher", ["C-6B"]); core.create_teacher("Mr Otieno", PW, "teacher", ["C-5G"]); core.create_teacher("Head Teacher", PW, "head")
TERMS = ["2025-T1", "2025-T2", "2025-T3", "2026-T1", "2026-T2", "2026-T3"]
SUBJ = ["Mathematics", "Science", "English", "Kiswahili", "Social Studies", "Creative Arts"]
# archetype -> (base, slope per term) per subject; None = default steady ~62
ARCH = {"stem": {"Mathematics": (66, 4), "Science": (64, 3.5), "English": (58, 0)}, "eng_fall": {"English": (68, -4.5)}, "steady": {}, "creative": {"Creative Arts": (82, .5), "Mathematics": (52, 0)},
        "lang": {"English": (74, 1), "Kiswahili": (76, 1)}, "decline": {s: (68, -3) for s in SUBJ}, "new": {}, "social": {"Social Studies": (74, 1.5)}}
LEARNERS = [("L-6B-01", "C-6B", "Amani K.", "stem"), ("L-6B-02", "C-6B", "Neema W.", "eng_fall"), ("L-6B-03", "C-6B", "Baraka O.", "steady"), ("L-6B-04", "C-6B", "Zawadi M.", "creative"),
            ("L-6B-05", "C-6B", "Juma A.", "lang"), ("L-6B-06", "C-6B", "Wanjiku N.", "stem"), ("L-6B-07", "C-6B", "Kiprop R.", "decline"), ("L-6B-08", "C-6B", "Aisha H.", "new"),
            ("L-6B-09", "C-6B", "Otieno P.", "steady"), ("L-6B-10", "C-6B", "Imani S.", "social"),
            ("L-5G-01", "C-5G", "Tendai M.", "stem"), ("L-5G-02", "C-5G", "Fatuma J.", "lang"), ("L-5G-03", "C-5G", "Brian N.", "steady"), ("L-5G-04", "C-5G", "Grace A.", "creative"), ("L-5G-05", "C-5G", "Salim Y.", "eng_fall"), ("L-5G-06", "C-5G", "Lucy K.", "social")]
NOTES = {"Mathematics": "Explained the method to a classmate", "Science": "Asked her own follow-up questions", "English": "Struggled with comprehension; absent that week", "Creative Arts": "Stays on task for long stretches when making things"}
for lid, cid, name, arch in LEARNERS:                       # register everyone first, so no write is left open between steps
    core.add_learner(lid, cid, name, "13-15" if lid in ("L-6B-01", "L-6B-05") else "9-12")
    if lid != "L-6B-09": core.set_consent(lid, "granted", "Ms Wanjiru" if cid == "C-6B" else "Mr Otieno")   # L-6B-09 deliberately has no consent
c = core.conn(); pend_ids = {}
for lid, cid, name, arch in LEARNERS:
    if lid == "L-6B-09": continue
    first = 5 if arch == "new" else 0
    for ti in range(first, 6):
        for s in SUBJ:
            b, sl = ARCH[arch].get(s, (62, 0)); sc = max(20, min(98, round(b + sl * ti + random.uniform(-4, 4))))
            kind = "project" if s in ("Science", "Creative Arts") and ti % 2 else "quiz"; note = NOTES.get(s, "") if (ti in (2, 5) and random.random() < .35) else ""
            atl = random.choice(["", "", "Thinking", "Research", "Communication", "Self-management"]) if note else ""
            status = "pending" if ti == 5 and lid in ("L-6B-01", "L-6B-03", "L-6B-05", "L-5G-01") else "approved"
            cur = c.execute("INSERT INTO evidence(learner,term,subject,kind,score,atl,note,teacher,status,created) VALUES(?,?,?,?,?,?,?,?,?,?)", (lid, TERMS[ti], s, kind, sc, atl, note, "Ms Wanjiru" if cid == "C-6B" else "Mr Otieno", status, 0))
            if status == "pending": pend_ids.setdefault(lid, []).append(cur.lastrowid)
c.commit()
import server   # seed two example proposals through the real tool so the approval queue is not empty
for lid in ("L-6B-01", "L-5G-01"):
    ids = " ".join(f"[E{i}]" for i in pend_ids[lid][:3])
    server.propose_update(lid, f"This term's results add to a steady picture {ids}. Which subjects did the learner enjoy most this term, and what would they like to try next?", "demo draft")
print(f"Demo school loaded into {core.DB}: 2 classes, 3 teachers, {len(LEARNERS)} learners. Logins: Ms Wanjiru / Mr Otieno / Head Teacher, password {PW}")
