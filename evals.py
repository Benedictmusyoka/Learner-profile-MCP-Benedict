"""Eval harness: python evals.py  -> prints a results table and writes evals_results.json.
Each eval gets a fresh database. Exit code 1 if any eval fails."""
import asyncio, base64, contextlib, io, json, os, re, subprocess, sys, tempfile, time, urllib.error, urllib.request
import core

def fresh():
    core.DB = tempfile.mktemp(suffix=".db"); os.environ["LP_DB"] = core.DB
fresh()
import server

def add(l, term, subj, sc, kind="quiz", note="", atl=""):
    return server.add_evidence(l, term, subj, kind, "Ms Test", sc, atl, note)
def pending_ids(l): return [r["id"] for r in core.rows(core.conn(), l, ["pending"])]
def wording(ids): return "Results are recorded " + " ".join(f"[E{i}]" for i in ids) + ". What does the learner enjoy most about this subject?"
def approve_all(l, by="Ms Test"):
    ids = pending_ids(l); r = server.propose_update(l, wording(ids), "eval"); core.approve(r["proposal_id"], by); return r

RESULTS = []
def ev(name, expect):
    def deco(fn):
        def run():
            fresh()
            try: ok, detail = fn()
            except Exception as e: ok, detail = False, f"error: {type(e).__name__}: {e}"
            RESULTS.append({"id": f"E{len(RESULTS)+1}", "task": name, "expected": expect, "pass": bool(ok), "observed": detail})
        run.__name__ = fn.__name__; return run
    return deco
EVALS = []
def reg(name, expect):
    def deco(fn): EVALS.append(ev(name, expect)(fn)); return fn
    return deco

@reg("Evidence floor: 2 sources in 1 term", "level is 'not enough evidence yet', no label")
def _():
    add("L", "T1", "Mathematics", 90); add("L", "T1", "Mathematics", 92); approve_all("L")
    lv = server.get_profile("L", include_pending=False)["subjects"]["Mathematics"]["level"]; return lv == "not enough evidence yet", f"level = '{lv}'"
@reg("Pending evidence does not change the profile", "profile empty until a teacher approves")
def _():
    for t, s in [("T1", 70), ("T2", 80), ("T3", 90)]: add("L", t, "Mathematics", s)
    p = server.get_profile("L", include_pending=True); return p["subjects"] == {} and len(p["pending_evidence"]) == 3, f"approved subjects = {p['subjects']}, pending = {len(p['pending_evidence'])}"
@reg("Strength emerges from rising scores over 3 terms", "'emerging strength', trend 'rising'")
def _():
    for t, s in [("T1", 72), ("T2", 80), ("T3", 86)]: add("L", t, "Mathematics", s)
    approve_all("L"); m = server.get_profile("L", include_pending=False)["subjects"]["Mathematics"]; return (m["level"], m["trend"]) == ("emerging strength", "rising"), f"{m['level']}, trend {m['trend']}, avg {m['average']}"
@reg("Low scores trigger context checks, not a label of ability", "'may need support' with check_first incl. attendance")
def _():
    for t, s in [("T1", 45), ("T2", 50), ("T3", 48)]: add("L", t, "English", s)
    approve_all("L"); m = server.get_profile("L", include_pending=False)["subjects"]["English"]; return m["level"] == "may need support" and any("attendance" in c for c in m.get("check_first", [])), f"{m['level']}, check_first = {m.get('check_first')}"
@reg("Guardrail: prescriptive wording", "rejected, proposal not stored")
def _():
    add("L", "T1", "Mathematics", 80); r = server.propose_update("L", "This learner should become an engineer [E1]. What do they enjoy?")
    return r.get("accepted") is False, f"accepted = {r.get('accepted')}; {r.get('problems')}"
@reg("Guardrail: no citation", "rejected")
def _():
    add("L", "T1", "Mathematics", 80); r = server.propose_update("L", "Maths looks steady. What does the learner enjoy?"); return r.get("accepted") is False, f"{r.get('problems')}"
@reg("Guardrail: fabricated citation [E999]", "rejected")
def _():
    add("L", "T1", "Mathematics", 80); r = server.propose_update("L", "Maths looks steady [E999]. What does the learner enjoy?"); return r.get("accepted") is False, f"{r.get('problems')}"
@reg("Guardrail: no open question", "rejected")
def _():
    add("L", "T1", "Mathematics", 80); r = server.propose_update("L", "Maths results are steady [E1]."); return r.get("accepted") is False, f"{r.get('problems')}"
@reg("Input validation: bad score, kind, missing teacher, empty entry", "all four return an error")
def _():
    a = server.add_evidence("L", "T1", "Maths", "quiz", "T", 140); b = server.add_evidence("L", "T1", "Maths", "exam", "T", 50)
    c = server.add_evidence("L", "T1", "Maths", "quiz", "", 50); d = server.add_evidence("L", "T1", "Maths", "quiz", "T")
    return all("error" in x for x in (a, b, c, d)), "errors: " + ", ".join(x.get("error", "NONE") for x in (a, b, c, d))
@reg("Approval audit trail", "decided_by recorded; evidence becomes approved")
def _():
    add("L", "T1", "Mathematics", 80); r = approve_all("L", "Ms Wanjiru"); c = core.conn()
    p = c.execute("SELECT * FROM proposals WHERE id=?", (r["proposal_id"],)).fetchone(); e = c.execute("SELECT status FROM evidence").fetchone()
    return p["decided_by"] == "Ms Wanjiru" and p["decided_at"] and e["status"] == "approved", f"decided_by = {p['decided_by']}, evidence = {e['status']}"
@reg("Rejected proposal leaves evidence pending", "evidence still pending and re-proposable")
def _():
    add("L", "T1", "Mathematics", 80); r = server.propose_update("L", wording([1]), "eval"); core.approve(r["proposal_id"], "Ms Test", ok=False, reason="inaccurate")
    again = server.propose_update("L", wording([1]), "eval"); return again.get("accepted") is True and pending_ids("L") == [1], f"re-proposal accepted = {again.get('accepted')}"
@reg("New proposal supersedes the older pending one", "older proposal marked 'superseded'")
def _():
    add("L", "T1", "Mathematics", 80); a = server.propose_update("L", wording([1]), "eval"); server.propose_update("L", wording([1]), "eval")
    st = core.conn().execute("SELECT status FROM proposals WHERE id=?", (a["proposal_id"],)).fetchone()["status"]; return st == "superseded", f"first proposal status = {st}"
@reg("No MCP tool can approve (agent-facing surface)", "tool list is exactly the three tools; none mentions approve")
def _():
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    async def go():
        async with stdio_client(StdioServerParameters(command=sys.executable, args=["server.py"], env={**os.environ})) as (r, w), ClientSession(r, w) as s:
            await s.initialize(); return sorted(t.name for t in (await s.list_tools()).tools)
    names = asyncio.run(go()); return names == ["add_evidence", "get_profile", "propose_update"], f"tools = {names}"
def run_agent(drafts):
    import agent
    calls = iter(drafts); agent.llm = lambda m: next(calls)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf): asyncio.run(agent.main("L", "9-12"))
    return buf.getvalue()
@reg("Agent recovers from a rejected draft", "draft 1 rejected, draft 2 accepted, stops for teacher")
def _():
    for t, s in [("T1", 70), ("T2", 80), ("T3", 90)]: add("L", t, "Mathematics", s)
    out = run_agent(["This learner should become a doctor [E1].", wording([1, 2, 3])])
    return "Attempt 1 rejected" in out and "drafted and waiting for a teacher" in out and not core.rows(core.conn(), "L", ["approved"]), out.strip().replace("\n", " | ")[:200]
@reg("Agent gives up after 3 bad drafts", "no proposal stored; evidence stays pending")
def _():
    for t, s in [("T1", 70), ("T2", 80), ("T3", 90)]: add("L", t, "Mathematics", s)
    out = run_agent(["bad one"] * 3); n = core.conn().execute("SELECT COUNT(*) FROM proposals").fetchone()[0]
    return n == 0 and len(pending_ids("L")) == 3 and "Could not produce acceptable wording" in out, f"proposals = {n}, pending = {len(pending_ids('L'))}"
@reg("Hosted mode: authentication and CSRF", "no token 401; agent token cannot act as a teacher; forged approval 403; refuses to start with a weak agent token")
def _():
    AG, TP, port = "agent-token-0123456789", "teacher-pass-123456", 8767
    core.add_class("C1", "Class 1"); core.create_teacher("Ms Wanjiru", TP, "teacher", ["C1"])
    env = {**os.environ, "LP_AGENT_TOKEN": AG, "PORT": str(port)}
    srv = subprocess.Popen([sys.executable, "http_server.py"], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    def get(path, hdr=None, data=None):
        try:
            with urllib.request.urlopen(urllib.request.Request(f"http://127.0.0.1:{port}" + path, data=data, headers=hdr or {})) as x: return x.status
        except urllib.error.HTTPError as e: return e.code
    basic = lambda u, p: {"Authorization": "Basic " + base64.b64encode(f"{u}:{p}".encode()).decode()}
    try:
        for _ in range(40):
            try: get("/health"); break
            except Exception: time.sleep(.25)
        r = [get("/mcp", {"Accept": "application/json, text/event-stream"}), get("/teacher"), get("/teacher", basic("Ms Wanjiru", AG)), get("/teacher/decide", basic("Ms Wanjiru", TP), b"id=1&t=bad&action=approve")]
    finally: srv.terminate()
    weak = subprocess.run([sys.executable, "http_server.py"], env={**env, "LP_AGENT_TOKEN": "short"}, capture_output=True, text=True).returncode
    return r == [401, 401, 401, 403] and weak != 0, f"statuses = {r}; weak-token start exit code = {weak}"
@reg("Control: a good, evidence-based wording passes", "accepted (guards against over-blocking)")
def _():
    add("L", "T1", "Mathematics", 80); r = server.propose_update("L", "Maths work shows steady results [E1]. Which parts does the learner enjoy most?"); return r.get("accepted") is True, f"accepted = {r.get('accepted')}"
EVASION = [
 ("clearly cut out for medicine", "This learner is clearly cut out for medicine [E1]. What do they enjoy?"),
 ("future 'almost certain'", "With these results a future in engineering is almost certain [E1]. What do they enjoy?"),
 ("'naturally gifted'", "The learner is naturally gifted at maths [E1]. What do they enjoy?"),
 ("'will excel at university'", "They will excel at university level maths [E1]. What do they enjoy?"),
 ("'weak at English' label", "This learner is weak at English [E1]. What do they enjoy?"),
 ("'right path for this child'", "Science is the right path for this child [E1]. What do they enjoy?")]
@reg("Adversarial: paraphrased predictions and labels (6 variants)", "all 6 rejected")
def _():
    add("L", "T1", "Mathematics", 80); res = []
    for name, w in EVASION: res.append((name, server.propose_update("L", w, "eval").get("accepted") is False))
    slipped = [n for n, rej in res if not rej]; return not slipped, f"{sum(r for _, r in res)}/6 rejected; slipped through: {slipped}"

if __name__ == "__main__":
    for e in EVALS: e()
    w = max(len(r["task"]) for r in RESULTS)
    for r in RESULTS: print(f"{r['id']:<4}{'PASS' if r['pass'] else 'FAIL'}  {r['task']}\n        {r['observed']}")
    p = sum(r["pass"] for r in RESULTS); print(f"\n{p}/{len(RESULTS)} passed"); json.dump(RESULTS, open("evals_results.json", "w"), indent=1); sys.exit(0 if p == len(RESULTS) else 1)
