---
status: active
author: stephen+claude
created: 2026-10-12
updated: 2026-10-12
---

# CONVENTIONS

## Canonical house standards

House defaults from the `ai-product-base` kit, verbatim for `retrofit-check.py`.
CLAUDE.md's own rules win where they differ, stated explicitly.

- **Free-only CI policy.** Read `_projects-admin/RULES.md` section 2.14 before changing workflows; shared gates enforce it: main/PR/manual triggers only, read-only tokens, job timeouts within 10 combined minutes, no schedules, matrices, services, artifact uploads or paid capacity, reviewed setup actions only, and Stop usage: Yes. Browser, coverage and mutation checks stay local. At 80% of the shared allowance, stop adding hosted work and report.

- **CI budget and pushes.** Run local validation before pushing, through the machine's shared hooks, never project copies. Automatic CI runs on PRs to main and pushes to main only. Batch finished work into planned pushes after the first branch backup, and re-run only failed jobs after diagnosis. Never silently disable CI or bypass a gate.

- **Publication false positives.** Stop and file the rule, path and a safe description in `_projects-admin/REQUESTS.md`, never the suspected secret; never rename code to dodge a heuristic. No blanket email-domain or dotted-string exemptions and no agent-approved exceptions.

- **Global rules and machine profiles are read-only here.** `~/.claude/*.md`, the Codex aliases and `_projects-admin/machines/` belong to `_projects-admin`; propose changes in its REQUESTS.md. Never write them by shell instead (redirects, `sed -i`, `tee`, `cp`, `mv` and `rm` included).

- **Spending money needs approval, per service, per session.** Paid APIs, generation, hosted inference and purchases prompt first; never route around a prompt with another tool or an unlisted endpoint.

- Push without asking: yes on a branch. For main, read the level in `ONBOARDING.md`: at L0/L1 prefer a branch per piece of work, then merge and push main without asking once checks pass (a plain commit or push to main needs no prompt); from L2 every main merge or push needs Stephen's approval. Force, chained, multi-refspec and delete pushes always ask.

Installed gates refuse rather than warn: a refusal is the answer. If a gate is genuinely wrong, say so and stop; the bypass is Stephen's. Verify enforcement per client and machine; documentation is not proof.

- Default branch is always `main`, never `master`

- Commit without asking: yes

- Create new top-level folders: no

- **Clean up after yourself: mess is yours, whoever made it.** Remove scratch files, temporary scripts, logs, failed output, duplicate checkouts and stray artefacts without asking, even another session's, but never uncommitted or unpushed work. Ask before removing anything published, supplied by Stephen, installed, roadmap-linked or tracked outside your change; archive media; list files before bulk changes. Finish with a clean `git status`.

- **Commit only this project's own work.** The kit's procedure (`RETROFIT.md`), global rules and other repositories' files are read where they live, never copied or committed here. Stage named paths when untracked files are not yours.

- One subagent at a time, never at your own tier or above

- **Never hack around a problem.** `any`, a cast, a suppression, a TODO, a second tool or a quieter check that hides a failure is cheating; if the real fix is blocked, stop and say so.

- An independent agent audits changes for bugs, broken code and overclaims before completion. Fix the findings and have the fixes re-audited before claiming done.

- When work passes between tools or sessions, use a work-item file in `handoffs/` copied from `handoffs/TEMPLATE.md`. The `owner` field is whose turn it is.

- **End replies where Stephen will see them.** Short replies; anything he must answer or do goes last, on its own, and the last line names what is still running (task id) or says nothing is. Never claim work is under way that nothing is running.

- **Keep the machine responsive.** Tests and builds use one or two workers, niced on the Mac; test, build, mutation and coverage jobs never overlap, an auditor's included. Run relevant checks while working and full suites once changes settle. One checkout per repository unless the desktop app or Stephen made the worktree.

- **Do it yourself; research before asking.** Run what you can instead of handing it to Stephen, and validate any command you give him. Check docs, records and earlier decisions first, and ask only for decisions genuinely his. A request to fix or pick up work is a request to do it.

- **Shared server controller.** Previews start, stop and report only through `<python> "<repos>/_projects-admin/scripts/project_control.py" status|start|stop` (append the project ID outside its checkout); start reuses the running server and never picks another port. Never launch dev servers, kill listeners or edit Tailscale routes yourself, or add project hooks. Register a new preview's unique ports through the admin workflow first.

- **One live address.** Give Stephen only this project's registered Tailscale link, never localhost or a port you picked; never start a second server or move ports. A server already on the registered port is the live one: use it or restart it on that port. Creating a project does not register it.

- **Vercel build policy.** Only main builds automatically; previews need Stephen's explicit request per branch, never wildcards. Apply `scripts/vercel-main-only.json` before connecting or pushing, as the kit's RETROFIT.md describes, and record exceptions in DECISIONS.md. CLI, API and deploy-hook builds need separate deployment authority.

- **Publication-safe records.** Everything tracked, commit metadata included, is fit to disclose: neutral decisions, no private conversation, profanity or emotional delivery; no credentials, contact details or machine paths (fixtures too); no em-dashes in public copy.

## Code baseline

- **User-facing copy checks.** Test the project's punctuation and brand rules against shipped copy and data, escaped characters included; the privacy scanner is not a typography checker.

- TypeScript runs with `strict: true` plus `noImplicitAny`, `noUncheckedIndexedAccess`, `exactOptionalPropertyTypes` and `useUnknownInCatchVariables`; never turn one off to pass.

- Python runs with `mypy` strict. Do not weaken project-wide strictness for one module.

- Never use `any` or `Any`. Prefer `unknown` and narrow it. No `@ts-ignore`.

- Typecheck, lint, and the project's tests must pass before that code is called done. Say exactly what did not run.

- When Stephen must apply SQL by hand, hand over every pending change for the task once, as one complete, idempotent script, never a change per turn or partial snippets.

- Preferred languages: TypeScript and Python. A new source file is `.ts` or `.tsx`; another runtime needs a one-line reason. Web code uses arrow functions and functional React components with hooks; exceptions are recorded decisions.

- Runtime-validate all untrusted input at system boundaries. Do not trust an external payload because it should be correct.

- No secrets in code or client bundles, including comments, tests, and fixtures.

- Explicit auth, ownership, and tenant-scope checks on every access boundary. The UI hiding a control is not the check.

- No unsafe raw-HTML injection without sanitisation and justification.

- No `@ts-ignore`, and no suppressions without reasons: `@ts-expect-error` with an inline reason is the only one, and only when the platform types are wrong.

- Prefer small modules with explicit inputs and outputs. Treat type, schema, and security warnings as real defects.

- Fail fast on invalid config, data, auth and permissions. Least privilege for credentials, APIs, storage and deployment.
