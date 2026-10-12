---
status: active
author: stephen+claude
created: 2026-10-12
updated: 2026-10-12
---

# CONVENTIONS

## Canonical house standards

House defaults from the `ai-product-base` kit (release 2026-10-R1), kept
verbatim so `_projects-admin/scripts/retrofit-check.py` can verify them.
CLAUDE.md holds this project's own rules and wins where they differ;
say so explicitly rather than silently.

- **Free-only CI policy.** Read `_projects-admin/RULES.md` section 2.14 before changing workflows. Shared Git gates check staged and outgoing workflow trees: main/PR/manual triggers, read-only Ubuntu jobs, at most 10 combined timeout minutes, distinct PR-cancelling/main-preserving groups and reviewed setup actions. No routine schedules, matrices, services, artifact uploads or paid capacity. Required browser, coverage and mutation checks stay local; reuse package scripts and propagate failures through a project test entry point. Run actionlint on workflow edits. Record dated account-wide headroom and measured monthly demand before expansion. Keep the zero paid budget; plan within 1,600 shared minutes plus a 400-minute reserve. At 80% usage stop adding non-essential hosted work and report, never silently disable required checks. Unknown headroom is not capacity. Normal edits do not retrofit untouched legacy CI.

- **CI budget and pushes.** Run the project's local validation before pushing; use the machine's shared hooks, never project hook copies. Keep automatic lightweight CI on PRs to main and pushes to main, not duplicate feature-branch pushes. Batch completed work into planned pushes without delaying the required initial branch backup. Cancel superseded PR runs, preserve each main publication range, set job timeouts and read-only token permissions. Re-run only failed jobs after diagnosis. Heavy browser, mutation and matrix jobs need a documented, bounded trigger; keep required local checks. Before enabling or expanding hosted CI, verify account-wide monthly headroom, runner costs, storage and a stop-usage budget with the account owner. Alerts alone are not a cap; unknown allowance is not spare capacity. Never silently disable CI or bypass a gate.

- **Publication false positives.** Stop and file the rule, path and a safe description in `_projects-admin/REQUESTS.md`; never include the suspected secret. Do not rename application symbols to evade a heuristic. Genuine public literals use the existing human-reviewed rule/path/value-hash exceptions on the remote default branch. No blanket email-domain or dotted-string exemptions, and no agent-approved exceptions.

- **Global rules and machine profiles are read-only here.** `~/.claude/*.md`, the Codex aliases and `_projects-admin/machines/` belong to `_projects-admin`. Append what belongs there, with evidence, to `_projects-admin/REQUESTS.md`. Do not reach for a shell to do what the editor refused: redirects, `sed -i`, `tee`, `cp`, `mv` and `rm` are covered too

- **Spending money needs approval, per service, per session.** Paid APIs, image and video generation, hosted inference and purchases all prompt first. Never route around a prompt with another tool or an unlisted endpoint

- Push without asking: yes on a branch. Main depends on the level declared in `ONBOARDING.md`. At L0 or L1, prefer a feature branch per piece of work, then merge it to main and push main without asking once its checks pass; a plain commit or a plain push to main needs no prompt. From L2, every main merge or push needs Stephen's approval, per instance. A force push, a chained command, a multi-refspec push and a delete refspec always ask, at every level

Installed gates refuse rather than warn. A refusal is the answer, not an obstacle to route around. If a gate is genuinely wrong, say so and stop: the bypass is Stephen's. Verify enforcement for each client and machine; documentation alone is not proof.

- Default branch is always `main`, never `master`

- Commit without asking: yes

- Create new top-level folders: no

- **Clean up after yourself: mess is yours, whoever made it.** Scratch files, temporary scripts, logs, failed or superseded output, duplicate checkouts and stray build artefacts are agent output. Remove them without asking, in this turn or a later one; another session having made them is no reason to leave them. Never remove a checkout or branch holding uncommitted or unpushed work, and archive creative and media assets rather than deleting them. Content is different: ask before removing anything published, anything Stephen supplied, installed skills or tools, roadmap-linked items, or tracked files outside your change. Bulk deletes, renames and moves list the exact files and their references first. Finish with `git status` showing only intended changes.

- One subagent at a time, never at your own tier or above

- **Never hack around a problem.** Solve it. `any`, a cast, a suppression, a TODO, a second tool, or a quieter check that hides the failure is cheating, and agents are not cheating. If the real fix is blocked, stop and say so.

- An independent agent audits changes for bugs, broken code and overclaims before completion. Fix the findings and have the fixes re-audited before claiming done.

- When work passes between tools or sessions, use a work-item file in `handoffs/` copied from `handoffs/TEMPLATE.md`. The `owner` field is whose turn it is.

- **End replies where Stephen will see them.** Keep replies short, with brief bullets for changes. Anything he must answer or do goes last, on its own. The final line names anything still running, with its task id, or says nothing is running. Never say work is under way unless a process or agent is actually running it.

- **Keep the machine responsive.** Tests and builds use one or two workers and run under `nice -n 10` on the Mac. Never overlap test, build, mutation or coverage jobs, including an auditor's. Run the relevant checks while working and the full suite once the changes settle. One working checkout per repository: switch branches rather than cloning or reinstalling per feature, unless the desktop app created the worktree or Stephen asked for one.

- **Do it yourself; research before asking.** Run any command, check or script you have the tools to run rather than handing it to Stephen. Any command you do give him was run or validated (for example with `--help`) in this session. Before asking, check the docs, the project's records and earlier decisions; ask only for a decision that is genuinely his and not already recorded. A request to fix, or to pick up work, is a request to do it, within scope.

- **Shared server controller.** Use `<python> "<repos>/_projects-admin/scripts/project_control.py" status` (or `start` / `stop`) from this registered checkout, or append its registered project ID. The controller and dashboard use the same daemon and registry; do not launch npm, Vite, Next or Python previews independently, kill their listeners directly, or rewrite Tailscale Serve routes. Start reuses an attributed running server and never selects another port. Before a new preview, register its existing command and unique local/Tailscale ports through the admin workflow; do not guess or duplicate ports. During retrofit, preserve the existing address and verify control in both directions. Shared machine hooks provide enforcement where the companion is installed; do not add project hooks.

- **One live address.** The switchboard registry holds the one port and the one Tailscale link for this project. That Tailscale link is the only address you give Stephen. Never send localhost, 127.0.0.1, or a port you picked. Do not start a second server. Do not move the app to a new port and call the registered port the old version. If a server is already listening on the registered port, that is the live one: use it, or stop it and start the same port again. Creating a project does not register it. A switchboard row is a separate step.

- **Vercel build policy.** Only main builds automatically; preview branches require Stephen's explicit request for this project and exact branch. When Vercel is selected, follow RETROFIT.md's Vercel build policy and apply scripts/vercel-main-only.json before connecting or pushing: replace git.deploymentEnabled in the effective Vercel config, preserving unrelated settings. Verify the production branch is main. Keep the deny-all default; never enable wildcard previews. Record each exception and its removal in DECISIONS.md. CLI/API/deploy-hook builds need separate deployment authority; Git permission is not deployment permission. Local previews use the shared server controller.

- **Publication-safe records.** Everything tracked, including commit metadata, must be suitable for disclosure. Record neutral decisions, not private conversation, profanity or the user's emotional delivery. Credentials, personal contact details and machine-specific paths stay outside Git, including fake-labelled fixtures. Nothing public-facing contains an em-dash.

## Code baseline

- **User-facing copy checks.** Test this project's declared punctuation and brand rules against application copy and shipped data, including escaped characters that render as prohibited punctuation. Keep technical literals and quoted source evidence outside that scope only through narrow, documented cases. Do not treat the shared privacy scanner as a typography checker.

- TypeScript runs with `strict: true`, plus `noImplicitAny`, `noUncheckedIndexedAccess`, `exactOptionalPropertyTypes`, and `useUnknownInCatchVariables`. Do not turn any of them off to get a file through.

- Python runs with `mypy` strict. Do not weaken project-wide strictness for one module.

- Never use `any` or `Any`. Prefer `unknown` and narrow it. No `@ts-ignore`.

- Typecheck, lint, and the project's tests must pass before that code is called done. Say exactly what did not run.

- When Stephen must apply SQL by hand, collect every pending change for the task into one complete, idempotent script and hand it over once, never a change per turn or partial snippets.

- Preferred languages: TypeScript and Python. Prefer TypeScript over vanilla JavaScript: a new source file is `.ts` or `.tsx`. Another runtime needs a one-line reason.

- Runtime-validate all untrusted input at system boundaries. Do not trust an external payload because it should be correct.

- No secrets in code or client bundles, including comments, tests, and fixtures.

- Explicit auth, ownership, and tenant-scope checks on every access boundary. The UI hiding a control is not the check.

- No unsafe raw-HTML injection without sanitisation and justification.

- No `@ts-ignore`. `@ts-expect-error` with an inline reason is the only suppression, and only when the platform types are wrong. No suppressions without reasons.

- Prefer small modules with explicit inputs and outputs. Treat type, schema, and security warnings as real defects.

- Fail fast on invalid config, invalid data, invalid auth, and permission violations. Use least privilege for credentials, APIs, storage, and deployment.
