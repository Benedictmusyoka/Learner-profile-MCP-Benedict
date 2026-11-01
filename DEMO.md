# Conference demo: 6 minutes

**Message:** a public-school teacher can have the continuous, cited learner record that only expensive systems give today, and still be the one who decides.

## Before you go on stage (10 minutes)

1. `git clone ... && cd learner-profile-mcp && python quickstart.py` once on the demo laptop, with internet. Confirm http://localhost:8000 opens and `Ms Wanjiru / demo-pass-1234` logs in.
2. Optional, for a real model: `ollama pull qwen2.5:7b`, start Ollama, rerun `quickstart.py`. The agent step then says "your local model". Without it the app uses a labelled stub, so say so if asked.
3. Open three tabs: Classes, Approvals, and the printed sheet for `L-6B-02`. Keep `learner_profile_demo.mp4` ready in case the laptop fails. Everything works offline once installed.
4. Reset any time: stop the app and run `python quickstart.py` again (it rebuilds `demo.db`).

## Run of show

| Min | Do | Say |
|---|---|---|
| 0:00 | Slide or voice only | "In an IB school a learner leaves primary with years of cited learning records. In a public school the same child has marks scattered across several teachers. A pattern obvious over four years is invisible one term at a time." |
| 0:45 | **Classes → Grade 6 Blue** | "Ordered by who may most benefit from a conversation. Kiprop's marks fell in every subject. Neema's English average is 60, which hides a drop to 50. These are fictional learners." |
| 1:45 | Open **Neema W.** | "Every line is cited. Look at the flag: *recent decline*. It comes with checks first: attendance, language of instruction, sight and hearing, home circumstances. A flag is a prompt, never a label." |
| 2:30 | Open **Otieno P.** | "No guardian consent is recorded, so the system refuses to record evidence. Consent is enforced in the database, not left to good intentions." |
| 3:00 | **Amani K.** → *Ask the local model to draft a summary* | "A local open-weights model drafts wording through an MCP server. The server rejects predictions and labels and requires citations. No cloud, no child data leaves the school." |
| 4:00 | **Approvals** → approve as Ms Wanjiru | "Only the teacher can approve, under their own account. The agent has a token but no account, so it can't approve its own work." |
| 4:45 | **Conversation sheet** for Neema | "This is what goes into the parent meeting. Questions, not conclusions. Decisions about subjects belong to the learner and the family." |
| 5:30 | Close | "This is a prototype. Next is a pilot with a real school, three terms, measuring whether teachers notice patterns earlier." |

## Say this before they ask

- **Is the AI deciding?** No. The model only drafts wording. The analysis is plain arithmetic. A teacher approves everything.
- **Is it accurate?** Unproven. Thresholds are starting guesses and nothing has been validated with real teachers or learners.
- **What about bias and labelling?** The wording guardrail is keyword matching and is **known to miss paraphrased predictions** (EVALS.md, E18). The teacher gate is the real safeguard today, and we are working on a better check.
- **Privacy?** Consent enforced, access by class, audit log, export and erasure, local models. Not yet independently reviewed.
- **Cost and scale?** One school server and a local model; no per-learner licence. One school per database today.
- **Does it work in Swahili?** Untested. Open-weights model quality in Swahili varies; testing it is part of the pilot.
