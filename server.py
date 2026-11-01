"""MCP server: learner profile tools. Agents can ADD and PROPOSE; only a named
teacher can APPROVE (approve.py). Run: python server.py  (stdio transport)"""
import json, time
from typing import Optional
from mcp.server.fastmcp import FastMCP
import core

mcp = FastMCP("learner-profile")

RULES = [
    "Describe demonstrated evidence; never predict or label the child.",
    "Cite every claim with its evidence id, e.g. [E12].",
    "Say 'not enough evidence yet' where the profile says so.",
    "For 'may need support', mention the check_first items before any interpretation.",
    "Write as questions and options for teacher, learner and family; pathways are their decision.",
    "Ages 9-12: activities and clubs, plain words. Ages 13-15: subject areas to explore, as examples.",
    "Include at least one open question.",
]

@mcp.tool()
def add_evidence(learner_id: str, term: str, subject: str, kind: str, teacher: str,
                 score: Optional[float] = None, atl_skill: str = "", note: str = "") -> dict:
    """Record one quiz, project or teacher note for a learner. It is stored as PENDING
    and does not affect the profile until a teacher approves a proposal containing it.
    kind: quiz | project | teacher_note. term like '2025-T2'. score 0-100 optional.
    atl_skill: Thinking | Research | Communication | Social | Self-management | ''."""
    if kind not in core.KINDS: return {"error": f"kind must be one of {sorted(core.KINDS)}"}
    if atl_skill not in core.ATL: return {"error": f"atl_skill must be one of {sorted(core.ATL)}"}
    if score is not None and not 0 <= score <= 100: return {"error": "score must be 0-100"}
    if score is None and not note.strip(): return {"error": "provide a score or a note"}
    if not (learner_id.strip() and term.strip() and subject.strip() and teacher.strip()):
        return {"error": "learner_id, term, subject and teacher are required"}
    c = core.conn()
    if core.strict() and not core.consent_ok(c, learner_id):
        return {"error": "learner is not registered or guardian consent is not recorded; ask the school administrator"}
    with c:
        cur = c.execute("INSERT INTO evidence(learner,term,subject,kind,score,atl,note,teacher,created)"
                        " VALUES(?,?,?,?,?,?,?,?,?)",
                        (learner_id, term, subject, kind, score, atl_skill, note.strip(), teacher, time.time()))
    return {"evidence_id": f"E{cur.lastrowid}", "status": "pending",
            "next": "call get_profile(include_pending=true), draft wording, then propose_update"}

@mcp.tool()
def get_profile(learner_id: str, age_band: str = "9-12", include_pending: bool = True) -> dict:
    """Return the sourced profile built ONLY from teacher-approved evidence, plus (optionally)
    pending evidence the model should consider when drafting. Not a verdict on the child."""
    c = core.conn()
    appr = core.rows(c, learner_id, ["approved"])
    prof = core.analyze(appr)
    last = c.execute("SELECT * FROM proposals WHERE learner=? AND status='approved' "
                     "ORDER BY decided_at DESC LIMIT 1", (learner_id,)).fetchone()
    out = {"learner_id": learner_id, "age_band": age_band, "basis": "teacher-approved evidence only",
           "evidence_floor": f">={core.MIN_SOURCES} sources across >={core.MIN_TERMS} terms",
           "subjects": prof, "atl_observed": core.atl_summary(appr),
           "approved_summary": None if not last else
               {"text": last["wording"], "approved_by": last["decided_by"], "proposal": last["id"]},
           "drafting_rules": RULES}
    if include_pending:
        pend = core.rows(c, learner_id, ["pending"])
        out["pending_evidence"] = [{"id": f"E{r['id']}", "term": r["term"], "subject": r["subject"],
            "kind": r["kind"], "score": r["score"], "atl": r["atl"], "note": r["note"], "by": r["teacher"]} for r in pend]
        out["if_pending_approved"] = core.analyze(appr + pend) if pend else None
    return out

@mcp.tool()
def propose_update(learner_id: str, wording: str, model_name: str = "unknown") -> dict:
    """Submit model-drafted wording for the profile update covering ALL currently pending
    evidence. The wording is checked by guardrails (citations, no prescriptive language,
    includes a question). If accepted it waits as a PENDING proposal for a named teacher
    to approve outside this agent. Nothing becomes part of the profile from this call."""
    c = core.conn()
    appr = core.rows(c, learner_id, ["approved"]); pend = core.rows(c, learner_id, ["pending"])
    if not pend: return {"error": "no pending evidence for this learner"}
    valid = {r["id"] for r in appr + pend}
    probs = core.lint_wording(wording, valid)
    if probs: return {"accepted": False, "problems": probs, "hint": "revise the wording and call again"}
    d = core.diff(core.analyze(appr), core.analyze(appr + pend))
    with c:
        c.execute("UPDATE proposals SET status='superseded' WHERE learner=? AND status='pending'", (learner_id,))
        cur = c.execute("INSERT INTO proposals(learner,evidence_ids,diff,wording,model,created) VALUES(?,?,?,?,?,?)",
                        (learner_id, json.dumps([r["id"] for r in pend]), json.dumps(d), wording, model_name, time.time()))
    return {"accepted": True, "proposal_id": cur.lastrowid, "status": "pending teacher approval",
            "diff": d, "next": f"STOP. A teacher runs: python approve.py approve {cur.lastrowid} --by 'YOUR NAME'"}

if __name__ == "__main__":
    mcp.run()
