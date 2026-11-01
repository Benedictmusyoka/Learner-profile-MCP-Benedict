# learner-profile-mcp

**Helping teachers spot a child's strengths and struggles in term 2, not at the national exam.**

A teacher web app and an [MCP](https://modelcontextprotocol.io) server that keep a lightweight, **cited, running record** of each learner's quizzes, projects and teacher notes, stored in a school database. A local open-weights model drafts plain-language summaries. A named teacher approves every update. The output is a sourced profile and conversation starters, never a verdict on the child.

## Run it (one command)

```bash
git clone https://github.com/<your-username>/learner-profile-mcp && cd learner-profile-mcp && python quickstart.py
```

Needs Python 3.10+ and internet for `pip`. It builds a virtualenv, loads a **fictional** demo school (2 classes, 16 learners, 6 terms of marks), has the agent draft a summary, then starts the web app at http://localhost:8000.
Log in as **Ms Wanjiru** (password `demo-pass-1234`) to see Grade 6 Blue, or **Head Teacher** to see every class. Uses a local [Ollama](https://ollama.com) model if one is running, otherwise a built-in stub (labelled "stub" in the app).

## What a teacher can do

| Page | What it does |
|---|---|
| Classes → class | Learners ordered by who may most benefit from a conversation: *worth a check-in*, awaiting approval, *emerging strengths*, steady, not enough evidence yet |
| Learner | Cited profile per subject with trend, pending evidence, add a mark or note, **Ask the local model to draft a summary** |
| Paste marks | Paste rows from a spreadsheet (learner_id, term, subject, kind, score, note). Entries are stored as *pending* |
| Approvals | Review drafted wording, the evidence behind it and the profile changes, then approve or reject under your own name |
| Conversation sheet | Printable page for a parent meeting: evidence, ideas to explore, context checks, questions. Ends with "not a verdict" |

## How it works

```
teacher marks -> [pending] -> agent drafts wording (local open-weights model) -> guardrails -> [proposal] -> TEACHER approves -> profile
```

- **Consent first.** In deployment mode, no evidence can be recorded for a learner unless a guardian's consent is recorded.
- **Evidence floor.** Fewer than 3 sources across 2 terms shows "not enough evidence yet", never a label.
- **Declines are not averaged away.** A subject whose recent marks fall below 60 and trend down is flagged *worth a check-in* even if the all-time average looks fine.
- **Context before conclusions.** A flag comes with checks to make first: attendance, language of instruction, sight and hearing, home or school circumstances.
- **Not prescriptive.** Wording is checked for citations and an open question, and for labelling or predictive phrases (see the known gap in [EVALS.md](EVALS.md)).
- **The agent can't approve.** Approval needs a teacher account; the agent has only a bearer token. See [ARCHITECTURE.md](ARCHITECTURE.md).

## Your data

Stored in one SQLite file (`learner.db`, owner-only permissions): classes, teachers (passwords hashed), learners (pseudonymous ID, optional first name and initial, age band, consent), evidence, proposals and an audit log.

- Teachers see only their assigned classes; a `head` role sees all. Another class's learner returns "not found".
- Every view, export, consent change and erasure is audit-logged.
- Export one learner as JSON; erase one learner and all their evidence (the audit log keeps only that it happened).
- Use pseudonymous IDs. Free-text notes can contain names, so tell teachers not to write them.

### School administrator commands

```bash
python manage.py add-class C-6B "Grade 6 Blue"
python manage.py add-teacher "Ms Wanjiru" --class C-6B          # asks for a password
python manage.py import-learners C-6B learners.csv              # columns: id,name,age_band
python manage.py consent L-6B-01 granted --by "Ms Wanjiru"
python manage.py export L-6B-01 > learner.json
python manage.py erase L-6B-01 --by "Head Teacher"
python manage.py backup backup.db                               # contains child data: store securely
python manage.py audit --last 50
```

## Run for a real school

```bash
LP_AGENT_TOKEN=<16+ random chars> LP_SECRET=<random> python http_server.py     # web app on :8000, MCP on /mcp
```

- **School server:** `docker-compose.yml` runs the app with a local Ollama model, no cloud needed (untested here, see below). Pull a model once: `docker compose exec ollama ollama pull qwen2.5:7b`.
- **Cloud:** `render.yaml` is a Render blueprint with a persistent disk.
- Put it behind HTTPS if it leaves the school network. See [docs/PILOT_PLAN.md](docs/PILOT_PLAN.md).

## Use with your own model or client

- Agent with a real model: `ollama pull qwen2.5:7b`, then `python agent.py L-6B-01`. Set `OLLAMA_MODEL` / `OLLAMA_HOST` to change. Against a hosted server: `MCP_URL=https://host/mcp LP_AGENT_TOKEN=... python agent.py L-6B-01`.
- Any MCP client (Claude Desktop, Cursor and others): command `python`, args `["/path/to/server.py"]`. Three tools: `add_evidence`, `get_profile`, `propose_update`.

## Tests and evals

`python test_v2.py` (school data, consent, access, privacy), `python test_e2e.py`, `python test_http.py`, `python evals.py`. Results and one **known, unfixed guardrail failure** are in [EVALS.md](EVALS.md).

## Honest limits

A prototype. Tested with synthetic data and a stub drafter, not a real model or real teachers. Pattern thresholds are starting guesses. Login is HTTP Basic with no sessions, logout or rate limiting. The pattern analysis is simple arithmetic, not a validated measure of aptitude: it supports a conversation, it does not measure a child. Real use needs guardian consent, a privacy review and a security review.

Docs: [DEMO.md](DEMO.md) (conference run-of-show) · [docs/PILOT_PLAN.md](docs/PILOT_PLAN.md) · [ARCHITECTURE.md](ARCHITECTURE.md) · [EVALS.md](EVALS.md)

## License

[MIT](LICENSE)
