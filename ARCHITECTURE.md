# Architecture

One agent, one custom MCP server, a school database, and a human gate.

```
Teacher (web app, per-teacher login) --+                        +--> local LLM (Ollama, open weights)
   log marks · paste CSV · approve     |                        |
                                       v                        | HTTP
                       web.py + http_server.py   <--MCP-->  Drafting agent (agent.py)
                       core.py: analysis, guardrails, access, consent
                                       |
                                  SQLite (learner.db)
Administrator: manage.py (classes, teachers, learners, consent, export, erase, backup)
```

## Agent shape

A single agent written as a plain Python loop, no framework: read the profile (`get_profile`), ask the local model to draft, submit (`propose_update`), and on a guardrail rejection feed the reasons back and retry, at most 3 times. Then stop. The script chooses the tools; the model only writes text. For a tool that touches children's records, a fixed sequence is easier to audit than a model choosing its own path. The web app's "draft" button runs this same agent, so there is one drafting path.

## MCP servers: built versus borrowed

| | What | Why |
|---|---|---|
| **Built** | `learner-profile`: `add_evidence`, `get_profile`, `propose_update`. Stdio locally; streamable HTTP in hosted mode behind a bearer token. | The domain rules live here: consent check, evidence floor, citations on every claim, no labelling wording, pending-until-approved. Any client or model gets the same checks. |
| **Borrowed** | None. | A generic database or filesystem MCP server would give an agent raw write access to learner records and bypass consent and approval. A hosted third-party server would send child data to someone else. |

Borrowed infrastructure: the official `mcp` SDK (pinned `<2`), Starlette and uvicorn, Ollama, SQLite. Not implemented: MCP resources and prompts. I did not audit the wider MCP ecosystem for a closer fit; the decision rests on the privacy and approval requirements.

## Data layer (SQLite, `core.py`)

| Table | Holds |
|---|---|
| `classes`, `teachers`, `teacher_classes` | Who may see what. Passwords are PBKDF2-hashed; roles are `teacher` or `head`. |
| `learners` | Pseudonymous ID, class, optional display name, age band, **consent status, who recorded it, when** |
| `evidence` | Quiz, project or note per learner, with status `pending`, `approved` or `discarded` |
| `proposals` | Drafted wording, the profile diff, drafting model, decision, decider |
| `audit` | Views, exports, consent changes, imports, approvals, erasures |

SQLite fits one school on one machine. For many schools, move to Postgres: all queries sit in `core.py` and `web.py`.

## Why approval is not an MCP tool

Approval needs a teacher account in the database, checked per request, and the teacher must be assigned to that learner's class. The agent holds only the bearer token, so it has no tool and no credential that can approve. Forms carry per-action anti-forgery tokens. `approve.py` remains as an administrator command-line path.

## Known limits

The wording guardrail is keyword matching and is known to miss paraphrased predictions (E18 in [EVALS.md](EVALS.md)). The pattern analysis is arithmetic, not a validated psychometric method. HTTP Basic login has no sessions, logout or rate limiting. Tested with a stub drafter, not a real model or an external MCP client. Docker files are untested.
