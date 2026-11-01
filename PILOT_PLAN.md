# Pilot plan: does a running, cited record help teachers notice patterns sooner?

This is a **plan, not a result**. No pilot has been run, and nothing here is evidence of impact yet.

## Question and hypothesis

If a public-school teacher keeps a lightweight, cited record across terms, patterns of strength and struggle become visible after about two terms instead of at the national exam, and guidance conversations with learners and families improve. The pilot tests whether that holds in practice and what it costs in teacher time.

## Setting (proposed)

1 to 2 public primary or lower-secondary schools; about 3 classes (roughly 100 learners) across Grades 5 to 7; one academic year (3 terms). A school server (a laptop or mini PC) on the school network runs the app and a local open-weights model. No internet is needed after installation, and no data leaves the school.

## Roles

School lead (sponsor), participating teachers, a school administrator (accounts, consent, backups), a data-protection lead for the school, and an independent evaluator who is not the developer.

## Workflow per term

1. **Term 0:** import class lists (`manage.py import-learners`), run guardian consent, create teacher accounts, train teachers (about 90 minutes).
2. **Each assessment:** the teacher pastes marks or adds notes (target: about 10 minutes per batch).
3. **Weekly:** the teacher reviews drafted summaries under Approvals (about 15 minutes).
4. **Mid-term:** the class page shows who is *worth a check-in*; the teacher checks context first (attendance, language, sight and hearing, circumstances).
5. **End of term:** conversation sheets for learners the teacher chooses, used at parent days and, for ages 13 to 15, subject-choice discussions.

## What to measure

Measure a baseline in Term 0, before the tool is used, then compare. Targets are to be agreed with the school; none are claimed here.

| Measure | How |
|---|---|
| Time to first sufficient-evidence pattern per learner | Terms until a subject reaches the evidence floor, versus when the teacher says they would otherwise have noticed |
| Teacher time per entry and per week | Teacher log and observation |
| Learners with a sufficient record by end of Term 2 | Count from the database |
| Check-in conversations held, and what followed | Teacher-recorded outcomes (support offered, context found, no action) |
| Usefulness and trust | Teacher survey each term; learner and family feedback on the conversation sheet |
| Draft quality | Share of drafts rejected by guardrails and by teachers, and why |
| Consent rate and complaints | Administrator log |

## Safeguards

- Guardian consent before any data is recorded; withdrawal stops new entries, and the school can erase the learner's data on request.
- Pseudonymous IDs; first names optional; teachers told not to write names in notes.
- Access limited by class; audit log reviewed by the data-protection lead each term.
- No automated decisions: the tool never selects, ranks or places a learner. Pathways remain the learner's and family's decision.
- Retention: agree a rule with the school (for example delete when the learner leaves), and document it.
- Legal: confirm obligations under Kenya's Data Protection Act 2019 for processing children's data, including any registration duty, and any Ministry of Education guidance on learner assessment records. This plan does not give legal advice.

## Risks to watch

- **Labelling and self-fulfilling expectations:** conversation sheets stay as questions; review a sample each term for predictive or limiting language.
- **Bias:** scores reflect language of instruction, absence and home circumstances. Flags prompt checks, not conclusions. Review whether suggestions skew by gender or subject, if the school agrees to collect that.
- **Guardrail gap:** the wording check misses paraphrased predictions (EVALS.md, E18). The teacher reads every draft until a better check is tested.
- **Workload:** if entry takes much longer than about 10 minutes per batch, adoption fails. Track it from week one.
- **Model quality:** open-weights models vary in Swahili and in following the rules. Test the chosen model on real notes before term 1.

## Needed before a real pilot

Real-model testing; fix or replace the wording guardrail; per-user sessions with logout and rate limiting; HTTPS if used beyond the school network; a tested backup and restore routine; an independent security and privacy review; accessible screens for low-end devices.

## Stop and go

Pause immediately on a privacy incident or a learner harmed by a label. After Term 2, continue only if teachers are using it and report it as useful; otherwise revise or stop.
