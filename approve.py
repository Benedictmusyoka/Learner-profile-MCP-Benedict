"""Teacher-only approval gate (human in the loop). Deliberately NOT an MCP tool.
  python approve.py list | show ID | approve ID --by NAME | reject ID --by NAME [--reason T] [--discard]"""
import argparse, json
import core

def show(c, p):
    print(f"\nProposal #{p['id']} · learner {p['learner']} · drafted by {p['model']} · {p['status']}")
    print("Wording:\n  " + p["wording"])
    print("Profile changes:", json.dumps(json.loads(p["diff"]), indent=2))
    for i in json.loads(p["evidence_ids"]):
        e = c.execute("SELECT * FROM evidence WHERE id=?", (i,)).fetchone()
        print(f"  [E{i}] {e['term']} {e['subject']} {e['kind']} score={e['score']} by {e['teacher']}: {e['note']}")

ap = argparse.ArgumentParser(); sub = ap.add_subparsers(dest="cmd", required=True)
sub.add_parser("list")
for n in ("show", "approve", "reject"):
    s = sub.add_parser(n); s.add_argument("id", type=int)
    if n != "show": s.add_argument("--by", required=True, help="your name, recorded in the audit trail")
    if n == "reject": s.add_argument("--reason", default=""); s.add_argument("--discard", action="store_true")
a = ap.parse_args(); c = core.conn()
if a.cmd == "list":
    for p in c.execute("SELECT id,learner,model,created FROM proposals WHERE status='pending'"):
        print(f"#{p['id']}  learner {p['learner']}  drafted by {p['model']}")
elif a.cmd == "show": show(c, c.execute("SELECT * FROM proposals WHERE id=?", (a.id,)).fetchone())
else:
    show(c, c.execute("SELECT * FROM proposals WHERE id=?", (a.id,)).fetchone())
    if input(f"\n{a.cmd} this proposal as '{a.by}'? [y/N] ").lower() == "y":
        core.approve(a.id, a.by, a.cmd == "approve", getattr(a, "reason", ""), getattr(a, "discard", False))
        print("Recorded.")
