"""Teacher web app (server-rendered HTML). Login = HTTP Basic against per-teacher accounts in the database.
A teacher only sees classes they are assigned to; a 'head' role sees all. Mounted by http_server.py."""
import asyncio, base64, csv, hashlib, hmac, html, io, json, os, subprocess, sys, time, urllib.request
from pathlib import Path
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, PlainTextResponse, RedirectResponse
import core
from server import add_evidence

ROOT = Path(__file__).resolve().parent
E = html.escape
KEY = (os.environ.get("LP_SECRET") or os.environ.get("LP_AGENT_TOKEN", "") + "|csrf").encode()
SUBJECTS = ["Mathematics", "Science", "English", "Kiswahili", "Social Studies", "Creative Arts", "PE"]
CSS = """body{font:16px/1.5 system-ui,-apple-system,Segoe UI,sans-serif;margin:0;background:#faf7f2;color:#1f2a2e}
nav{background:#0f6e56;color:#fff;padding:.6rem 1rem;display:flex;gap:1.2rem;align-items:center;flex-wrap:wrap}nav a{color:#fff;text-decoration:none;font-weight:600}nav .rt{margin-left:auto;opacity:.85;font-size:14px}
main{max-width:980px;margin:0 auto;padding:1rem}h1{font-size:24px;margin:.6rem 0}h2{font-size:18px;margin:1.4rem 0 .4rem}
.card{background:#fff;border:1px solid #e3ddd2;border-radius:10px;padding:.8rem 1rem;margin:.6rem 0}
table{border-collapse:collapse;width:100%;background:#fff}td,th{border-bottom:1px solid #e3ddd2;padding:.5rem;text-align:left;font-size:15px;vertical-align:top}th{background:#e1f5ee}
.chip{display:inline-block;border-radius:99px;padding:1px 10px;font-size:13px;font-weight:600;margin:1px 3px 1px 0}.g{background:#e8f3e6;color:#2e7d32}.a{background:#faeeda;color:#b4540a}.n{background:#eeece6;color:#667075}.rd{background:#fcebeb;color:#a32d2d}.p{background:#eeedfe;color:#534ab7}
.mut{color:#667075;font-size:14px}input,select,textarea,button{font:inherit;padding:.4rem .6rem;border:1px solid #cfc9bc;border-radius:7px}button{background:#0f6e56;color:#fff;border:0;cursor:pointer}button.s{background:#fff;color:#1f2a2e;border:1px solid #cfc9bc}
.msg{background:#e1f5ee;border:1px solid #0f6e56;border-radius:8px;padding:.5rem .8rem;margin:.6rem 0}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:.6rem}
.w{background:#e1f5ee;padding:.6rem .8rem;border-radius:8px}a{color:#0f6e56}@media print{nav,.noprint{display:none}body{background:#fff}}"""

def who(req):
    try: u, pw = base64.b64decode(req.headers.get("authorization", "")[6:]).decode().split(":", 1)
    except Exception: return None
    role = core.verify_teacher(u, pw); return (u, role) if role else None
def need_login(): return PlainTextResponse("Teacher login required", 401, {"WWW-Authenticate": 'Basic realm="Learner Profile Assistant"'})
def tok(u, scope): return hmac.new(KEY, f"{u}|{scope}".encode(), hashlib.sha256).hexdigest()[:32]
def csrf_ok(u, scope, t): return hmac.compare_digest(str(t), tok(u, scope))
def chip(t, k="n"): return f'<span class="chip {k}">{E(t)}</span>'
def page(req, title, body, u=None, status=200):
    m = req.query_params.get("msg", "") if req else ""
    nav = f'<nav><a href="/classes">Classes</a><a href="/teacher">Approvals</a><span class="rt">{E(u[0])} · {E(u[1])}</span></nav>' if u else ""
    return HTMLResponse(f'<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{E(title)}</title><style>{CSS}</style>{nav}<main>{"<div class=msg>" + E(m) + "</div>" if m else ""}{body}</main>', status)
def back(path, msg): return RedirectResponse(f"{path}?msg={urllib.request.quote(msg[:300])}", 303)
def lget(c, u, lid):
    return c.execute("SELECT * FROM learners WHERE id=?", (lid,)).fetchone() if core.can_access(c, u[0], lid) else None
def spark(pts):
    if len(pts) < 2: return ""
    xs = [p[0] for p in pts]; lo, hi = min(xs), max(xs) or 1
    d = " ".join(f"{4 + (x - lo) / max(1, hi - lo) * 112:.0f},{28 - y / 100 * 24:.0f}" for x, y in pts)
    return f'<svg width="120" height="32" aria-hidden="true"><polyline points="{d}" fill="none" stroke="#0f6e56" stroke-width="2"/></svg>'
LVK = {"emerging strength": "g", "may need support": "a"}

async def index(req): return RedirectResponse("/classes", 303)

async def classes(req):
    u = who(req)
    if not u: return need_login()
    c = core.conn()
    cl = c.execute("SELECT * FROM classes ORDER BY id").fetchall() if u[1] == "head" else c.execute("SELECT c.* FROM classes c JOIN teacher_classes t ON t.class_id=c.id WHERE t.teacher=? ORDER BY c.id", (u[0],)).fetchall()
    cards = ""
    for k in cl:
        ov = core.class_overview(c, k["id"])
        cards += f'<div class="card"><h2><a href="/class/{E(k["id"])}">{E(k["name"])}</a></h2><div class="mut">{len(ov)} learners</div>{chip(str(sum(1 for r in ov if r["support"])) + " worth a check-in", "a") if any(r["support"] for r in ov) else ""}{chip(str(sum(r["pending_proposals"] for r in ov)) + " awaiting your approval", "p") if any(r["pending_proposals"] for r in ov) else ""}</div>'
    return page(req, "Classes", "<h1>Your classes</h1>" + (cards or "<p>No classes are assigned to you yet. Ask the school administrator.</p>"), u)

async def class_page(req):
    u = who(req)
    if not u: return need_login()
    cid = req.path_params["cid"]; c = core.conn()
    if not core.can_access_class(c, u[0], cid): return page(req, "Not found", "<h1>Not found</h1>", u, 404)
    k = c.execute("SELECT * FROM classes WHERE id=?", (cid,)).fetchone(); rows = ""
    for r in core.class_overview(c, cid):
        ch = (chip("Worth a check-in: " + ", ".join(r["support"]), "a") if r["support"] else "") + (chip("Emerging: " + ", ".join(r["strong"]), "g") if r["strong"] else "")
        if not ch: ch = chip("Steady: no clear pattern yet" if r["enough"] else "Not enough evidence yet")
        cons = chip("consent recorded", "g") if r["consent"] == "granted" else chip("no consent: cannot record", "rd")
        rows += f'<tr><td><a href="/learner/{E(r["id"])}">{E(r["name"])}</a><div class="mut">{E(r["id"])}</div></td><td>{ch}</td><td>{r["approved"]} approved<br>{r["pending_evidence"]} pending</td><td>{cons}{chip(str(r["pending_proposals"]) + " to approve", "p") if r["pending_proposals"] else ""}</td></tr>'
    body = f'''<h1>{E(k["name"])}</h1><p class="mut">Ordered by who may most benefit from a conversation. These are prompts for a teacher, never labels for a child.</p>
<table><tr><th>Learner</th><th>What the approved evidence shows</th><th>Evidence</th><th>Status</th></tr>{rows}</table>
<h2>Paste marks from a spreadsheet</h2><form class="card" method="post" action="/class/{E(cid)}/import"><input type="hidden" name="t" value="{tok(u[0], "import:" + cid)}">
<div class="mut">Columns: learner_id, term, subject, kind, score, note (first row = headers). Entries are stored as pending until approved.</div>
<textarea name="csv" rows="6" style="width:100%;box-sizing:border-box" placeholder="learner_id,term,subject,kind,score,note&#10;L-6B-01,2026-T3,Mathematics,quiz,84,Geometry"></textarea><p><button>Import as pending</button></p></form>'''
    return page(req, k["name"], body, u)

async def class_import(req):
    u = who(req)
    if not u: return need_login()
    cid = req.path_params["cid"]; f = await req.form(); c = core.conn()
    if not csrf_ok(u[0], "import:" + cid, f.get("t", "")): return PlainTextResponse("bad token", 403)
    if not core.can_access_class(c, u[0], cid): return PlainTextResponse("not found", 404)
    ok, errs = 0, []
    for i, r in enumerate(csv.DictReader(io.StringIO(str(f.get("csv", ""))[:200_000])), 2):
        if i > 501: errs.append("stopped at 500 rows"); break
        r = {(k or "").strip().lower(): (v or "").strip() for k, v in r.items()}; lid = r.get("learner_id", "")
        if not c.execute("SELECT 1 FROM learners WHERE id=? AND class_id=?", (lid, cid)).fetchone(): errs.append(f"row {i}: {lid or '?'} is not in this class"); continue
        try: sc = float(r["score"]) if r.get("score") else None
        except ValueError: errs.append(f"row {i}: bad score"); continue
        res = add_evidence(lid, r.get("term", ""), r.get("subject", ""), r.get("kind") or "quiz", u[0], sc, r.get("atl", ""), r.get("note", ""))
        if "error" in res: errs.append(f"row {i}: {res['error']}")
        else: ok += 1
    with c: core.audit(c, u[0], "import_csv", cid, f"{ok} ok, {len(errs)} rejected")
    return back(f"/class/{cid}", f"Imported {ok} entries as pending; {len(errs)} rejected. " + "; ".join(errs[:3]))

async def learner(req):
    u = who(req)
    if not u: return need_login()
    lid = req.path_params["lid"]; c = core.conn(); l = lget(c, u, lid)
    if not l: return page(req, "Not found", "<h1>Not found</h1>", u, 404)
    with c: core.audit(c, u[0], "view_learner", lid)
    appr = core.rows(c, lid, ["approved"]); pend = core.rows(c, lid, ["pending"]); A = core.analyze(appr)
    terms = sorted({r["term"] for r in appr}); cards = ""
    for s, v in A.items():
        by = {}
        for r in appr:
            if r["subject"] == s and r["score"] is not None: by.setdefault(r["term"], []).append(r["score"])
        pts = [(terms.index(t), sum(x) / len(x)) for t, x in by.items()]
        chk = f'<div class="mut" style="color:#b4540a">Why flagged: {E(v.get("reason", ""))}. Check first: {E(", ".join(v["check_first"]))}</div>' if v.get("check_first") else ""
        cards += f'<div class="card"><b>{E(s)}</b> {chip(v["level"], LVK.get(v["level"], "n"))}{chip(v["trend"]) if v["trend"] else ""}<div class="mut">{v["sources"]} sources over {v["terms"]} terms{"" if v["average"] is None else ", average " + str(v["average"]) + "%"} · {E(" ".join("[" + e + "]" for e in v["evidence_ids"]))}</div>{spark(pts)}{chk}</div>'
    last = c.execute("SELECT * FROM proposals WHERE learner=? AND status='approved' ORDER BY decided_at DESC LIMIT 1", (lid,)).fetchone()
    summ = f'<div class="w">{E(last["wording"])}<div class="mut">Approved by {E(last["decided_by"])} · drafted by {E(last["model"])}</div></div>' if last else '<p class="mut">No approved summary yet.</p>'
    pe = "".join(f'<tr><td>E{r["id"]}</td><td>{E(r["term"])}</td><td>{E(r["subject"])}</td><td>{E(r["kind"])}</td><td>{"" if r["score"] is None else r["score"]}</td><td>{E(r["note"] or "")}</td></tr>' for r in pend)
    consent = l["consent_status"] == "granted"
    form = f'''<form class="card" method="post" action="/learner/{E(lid)}/evidence"><input type="hidden" name="t" value="{tok(u[0], "ev:" + lid)}">
<div style="display:flex;gap:.5rem;flex-wrap:wrap"><input name="term" placeholder="Term e.g. 2026-T3" required><input name="subject" list="subj" placeholder="Subject" required><datalist id="subj">{"".join("<option>" + s + "</option>" for s in SUBJECTS)}</datalist>
<select name="kind"><option>quiz</option><option>project</option><option>teacher_note</option></select><input name="score" type="number" min="0" max="100" step="any" placeholder="Score %">
<select name="atl"><option value="">ATL skill</option><option>Thinking</option><option>Research</option><option>Communication</option><option>Social</option><option>Self-management</option></select></div>
<p><textarea name="note" rows="2" style="width:100%;box-sizing:border-box" placeholder="What did you observe?"></textarea></p><button {"" if consent else "disabled"}>Record as pending</button> <span class="mut">Recorded under your name ({E(u[0])}). {"" if consent else "Disabled: guardian consent is not recorded for this learner."}</span></form>'''
    body = f'''<h1>{E(l["display_name"] or lid)} <span class="mut">{E(lid)} · ages {E(l["age_band"])}</span></h1>
<p><a href="/class/{E(l["class_id"])}">← class</a> · <a href="/learner/{E(lid)}/sheet">Conversation sheet</a> · <a href="/learner/{E(lid)}/export.json">Export data</a></p>
<h2>Approved summary</h2>{summ}<h2>Profile (approved evidence only)</h2>{cards or '<p class="mut">Nothing approved yet.</p>'}
<h2>Waiting for approval</h2>{('<table><tr><th>ID</th><th>Term</th><th>Subject</th><th>Type</th><th>Score</th><th>Note</th></tr>' + pe + '</table>') if pend else '<p class="mut">No pending evidence.</p>'}
<form method="post" action="/learner/{E(lid)}/draft" class="noprint"><input type="hidden" name="t" value="{tok(u[0], "draft:" + lid)}"><button class="s" {"" if pend else "disabled"}>Ask the local model to draft a summary</button> <span class="mut">Runs the same MCP agent. You still approve it under Approvals.</span></form>
<h2>Add evidence</h2>{form}'''
    return page(req, "Learner", body, u)

async def learner_evidence(req):
    u = who(req)
    if not u: return need_login()
    lid = req.path_params["lid"]; f = await req.form(); c = core.conn()
    if not csrf_ok(u[0], "ev:" + lid, f.get("t", "")): return PlainTextResponse("bad token", 403)
    if not lget(c, u, lid): return PlainTextResponse("not found", 404)
    try: sc = float(f["score"]) if f.get("score") else None
    except ValueError: return back(f"/learner/{lid}", "Score must be a number")
    r = add_evidence(lid, str(f.get("term", "")), str(f.get("subject", "")), str(f.get("kind", "quiz")), u[0], sc, str(f.get("atl", "")), str(f.get("note", "")))
    return back(f"/learner/{lid}", r.get("error") or f"Recorded as pending ({r['evidence_id']}).")

def ollama_up():
    try: urllib.request.urlopen(os.environ.get("OLLAMA_HOST", "http://localhost:11434") + "/api/tags", timeout=1); return True
    except Exception: return False
async def learner_draft(req):
    u = who(req)
    if not u: return need_login()
    lid = req.path_params["lid"]; f = await req.form(); c = core.conn(); l = lget(c, u, lid)
    if not csrf_ok(u[0], "draft:" + lid, f.get("t", "")): return PlainTextResponse("bad token", 403)
    if not l: return PlainTextResponse("not found", 404)
    if os.environ.get("DRAFTER") != "stub" and not ollama_up(): return back(f"/learner/{lid}", "The local model is not reachable. Start Ollama, or ask the administrator.")
    r = await asyncio.to_thread(subprocess.run, [sys.executable, str(ROOT / "agent.py"), lid, "--age", l["age_band"]], capture_output=True, text=True, timeout=420, env={**os.environ})
    out = r.stdout + r.stderr
    return back(f"/learner/{lid}", "Draft ready. Review it under Approvals." if "waiting for a teacher" in out else "No acceptable draft this time: " + out.strip().splitlines()[-1] if out.strip() else "No output from the agent.")

async def learner_export(req):
    u = who(req)
    if not u: return need_login()
    lid = req.path_params["lid"]; c = core.conn()
    if not lget(c, u, lid): return PlainTextResponse("not found", 404)
    with c: core.audit(c, u[0], "export_learner", lid)
    return JSONResponse(core.export_learner(c, lid), headers={"Content-Disposition": f'attachment; filename="{lid}.json"'})

CL = {"Mathematics": "STEM", "Science": "STEM", "English": "Language", "Kiswahili": "Language", "Social Studies": "Society", "Creative Arts": "Creative", "PE": "Active"}
TXT = {"STEM": ("{n} often seems to enjoy working things out. Puzzle clubs, building projects or science fairs could be fun to try.", "Maths and science show a steady pattern. Worth exploring what STEM-oriented subject combinations involve, and asking {n} which parts they enjoy."),
 "Language": ("{n} seems to enjoy words and ideas. Storytelling, debate or reading clubs might be a good fit.", "Language work shows a consistent pattern. Worth exploring subjects heavy on reading, writing and speaking, and asking {n} what kinds of communication they enjoy."),
 "Society": ("{n} shows interest in people and how communities work. Group projects or class roles could suit them.", "Social studies shows a pattern of interest in people and society. Worth looking at social science options and asking {n} what questions about the world interest them."),
 "Creative": ("{n} seems to enjoy making things. Drawing, design or craft activities could be worth encouraging.", "Creative work shows a consistent pattern. Worth looking at arts and design options and asking {n} what they like making."),
 "Active": ("{n} seems to shine in movement and teamwork. Sports teams or group games could be a good fit.", "Physical activity and teamwork show a pattern. Worth looking at sports and movement options and asking {n} what they enjoy about them.")}
async def sheet(req):
    u = who(req)
    if not u: return need_login()
    lid = req.path_params["lid"]; c = core.conn(); l = lget(c, u, lid)
    if not l: return page(req, "Not found", "<h1>Not found</h1>", u, 404)
    with c: core.audit(c, u[0], "view_sheet", lid)
    A = core.analyze(core.rows(c, lid, ["approved"])); n = (l["display_name"] or "the learner").split()[0]; o = 1 if l["age_band"] == "13-15" else 0
    last = c.execute("SELECT * FROM proposals WHERE learner=? AND status='approved' ORDER BY decided_at DESC LIMIT 1", (lid,)).fetchone()
    ev = "".join(f'<li><b>{E(s)}</b>: {E(v["level"])}{"" if v["average"] is None else ", average " + str(v["average"]) + "%"}{", " + v["trend"] if v["trend"] else ""} ({v["sources"]} sources over {v["terms"]} terms)</li>' for s, v in A.items())
    seen, st = set(), ""
    for s, v in A.items():
        k = CL.get(s)
        if v["level"] == "emerging strength" and k and k not in seen: seen.add(k); st += f"<p>{E(TXT[k][o].replace('{n}', n))}</p>"
    sup = [s for s, v in A.items() if v["level"] == "may need support"]
    sp = f'<p><b>Worth a check-in ({E(", ".join(sup))}).</b> Before reading anything into the marks, check attendance, language of instruction, sight and hearing, and what was happening at home or school. Ask: which parts feel hardest, and what help would feel useful?</p>' if sup else ""
    body = f'''<h1>Conversation sheet: {E(l["display_name"] or lid)}</h1><p class="mut">Prepared {time.strftime("%d %B %Y")} for {E(u[0])} · ages {E(l["age_band"])} <button class="noprint s" onclick="print()">Print</button></p>
<h2>What the approved evidence shows</h2><ul>{ev or "<li>Not enough approved evidence yet.</li>"}</ul>{('<h2>Summary</h2><div class="w">' + E(last["wording"]) + '</div>') if last else ""}
<h2>Ideas to explore together</h2>{st or '<p class="mut">No strengths have enough evidence yet.</p>'}{sp}
<h2>Questions to start the conversation</h2><ul><li>What did {E(n)} enjoy most this term, and what felt difficult?</li><li>What would {E(n)} like to try more of?</li><li>Where do you see {E(n)} spending time happily outside school?</li></ul>
<p class="mut">This sheet describes evidence recorded so far. It is a conversation starter, not a verdict. Decisions about subjects and pathways belong to the learner and family.</p>'''
    return page(None, "Conversation sheet", body, None)

async def approvals(req):
    u = who(req)
    if not u: return need_login()
    c = core.conn(); out = ""
    for p in c.execute("SELECT * FROM proposals WHERE status='pending' ORDER BY id"):
        if not core.can_access(c, u[0], p["learner"]): continue
        ln = c.execute("SELECT display_name FROM learners WHERE id=?", (p["learner"],)).fetchone()
        ev = "".join(f"<li>[E{i}] {E(e['term'])} {E(e['subject'])} {E(e['kind'])} score={e['score']} by {E(e['teacher'])}: {E(e['note'] or '')}</li>" for i in json.loads(p["evidence_ids"]) for e in [c.execute("SELECT * FROM evidence WHERE id=?", (i,)).fetchone()] if e)
        out += f'''<div class="card"><h2>Proposal #{p["id"]}: {E((ln["display_name"] if ln else "") or p["learner"])} <span class="mut">{E(p["learner"])} · drafted by {E(p["model"])}</span></h2><div class="w">{E(p["wording"])}</div>
<details><summary>Profile changes</summary><pre style="overflow:auto">{E(json.dumps(json.loads(p["diff"]), indent=1))}</pre></details><p class="mut">Evidence behind it:</p><ul>{ev}</ul>
<form method="post" action="/teacher/decide"><input type="hidden" name="id" value="{p["id"]}"><input type="hidden" name="t" value="{tok(u[0], "decide:" + str(p["id"]))}"><input name="reason" placeholder="Reason (optional)"> <button name="action" value="approve">Approve as {E(u[0])}</button> <button class="s" name="action" value="reject">Reject</button></form></div>'''
    return page(req, "Approvals", "<h1>Pending proposals</h1><p class='mut'>Nothing enters a learner's profile until you approve it.</p>" + (out or "<p>Nothing is waiting for approval.</p>"), u)

async def decide(req):
    u = who(req)
    if not u: return need_login()
    f = await req.form(); c = core.conn()
    try: pid = int(f["id"])
    except Exception: return PlainTextResponse("bad request", 400)
    if not csrf_ok(u[0], "decide:" + str(pid), f.get("t", "")): return PlainTextResponse("bad token", 403)
    p = c.execute("SELECT * FROM proposals WHERE id=?", (pid,)).fetchone()
    if not p or not core.can_access(c, u[0], p["learner"]): return PlainTextResponse("not found", 404)
    try: core.approve(pid, u[0], f.get("action") == "approve", str(f.get("reason", ""))[:300])
    except ValueError as e: return PlainTextResponse(str(e), 409)
    return RedirectResponse("/teacher", 303)

def register(app):
    for path, fn, m in [("/", index, ["GET"]), ("/classes", classes, ["GET"]), ("/class/{cid}", class_page, ["GET"]), ("/class/{cid}/import", class_import, ["POST"]),
                        ("/learner/{lid}", learner, ["GET"]), ("/learner/{lid}/evidence", learner_evidence, ["POST"]), ("/learner/{lid}/draft", learner_draft, ["POST"]),
                        ("/learner/{lid}/export.json", learner_export, ["GET"]), ("/learner/{lid}/sheet", sheet, ["GET"]), ("/teacher", approvals, ["GET"]), ("/teacher/decide", decide, ["POST"])]:
        app.add_route(path, fn, methods=m)
