---
status: active
author: stephen+claude
created: 2026-08-19
updated: 2026-10-08
note: "Canonical self-contained import and retrofit guidance for one authorised project."
generated_by: claude
generated_at: 2026-09-20T14:06Z
generated_from: conversation
---

# Import and retrofit guidance

## The entire user instruction

For a new project, Stephen can say: **"Import `ai-product-base` and follow its
guidance"** (or `ai-creative-base`). For an existing project he can say:
**"Retrofit this project using `ai-product-base` and follow its guidance"**.
Those are complete instructions. The receiving agent reads this file from the
chosen template and performs the applicable path below; Stephen does not have
to locate or reproduce an operator checklist.

For an empty or new target, copy the whole chosen template, read `CLAUDE.md`
and its start requirements, replace the template placeholders, then run
`scripts/bootstrap.sh` and follow the start sequence. For an existing target,
use the merge procedure below. Never overwrite mature project rules or working
files with a blind copy. Both paths must complete the applicable Vercel build
policy below before their first Vercel-connected push or project connection.

Work one authorised project at a time. Preserve mature rules and working files;
a static report is not proof of runtime enforcement.

## Paths and interpreters

`<repos>` means the actual Repos directory containing `_projects-admin` and
`_Ai`, not the user's home. `<project>` is the explicitly authorised target.
`<python>` is `python3.13` on the Mac, `python` or `py` on the PC. Never use the
Windows `python3` Store stub. Quote paths containing spaces. Run shell scripts
through Git Bash on Windows. Commands below run from the target project unless
a different directory is stated.

## Canonical kit

Choose `_projects-admin/templates/ai-product-base` for development or
`templates/ai-creative-base` for creative production. Vendor from this canonical
source. Global rules (`HOUSE-RULES.md`) and the nine-class audit checklist
(`STANDARDS-AUDIT.md`) live in `_projects-admin` too, since the separate
`ai-standards` repo was folded in on 2026-09-09. The global bootstrap is a separate once-per-machine installation,
not a project retrofit.

## Procedure

1. **Record state and read local rules.** Report branch, dirty files and
   ahead/behind and remote branches. Preserve existing work. Read the project's
   rules and required documents, then establish its declared level or creative
   stage and Git policy. Product L0/L1 prefers a feature branch, merged to main
   and pushed with standing permission once checks pass.
   L2+ and creative defaults use a fresh feature branch from current main.
   Resolve missing/conflicting declarations once; never downgrade a live project.
   Record the source kit commit and propose the exact changes. Push feature
   branches as backup after applying the Vercel policy below when connected;
   outside product L0/L1, main needs express permission.
2. **Check just this target.** Run
   `<python> "<repos>/_projects-admin/scripts/retrofit-check.py" --project "<project>"`.
   This command is read-only. Keep the initial gap report. Declare `project_kind: product`
   or `creative` in ONBOARDING.md frontmatter; absence is not creative. Use
   `--kind` only after resolving ambiguity. This is a static check;
   it cannot prove live hooks, global policy or every project-specific rule.
3. **Merge the rules.** Make CLAUDE.md authoritative, preserving real rules from
   AGENTS.md and leaving AGENTS.md a short pointer. Include autonomy, the necessary
   read list, independent audit before done, and a handoff/archiving convention.
   Merge the canonical standards from template CONVENTIONS.md and make it a
   mandatory read for every client. Compare complete rule bodies, not headings.
   Bring over relevant procedures, not unrelated product levels or
   creative stage gates. List any new directories in the project's structure.
4. **Prepare old documents before enabling gates.** Review a dry-run diff for
   em-dashes, then use spaced hyphens in prose/copy. Preserve technical literals
   where changing them would alter behaviour. Add house frontmatter to markdown
   documents: status, author and applicable dates. Declare justified extra statuses
   and word-budget overrides in the project contract. Archive superseded material
   through the project's existing procedure, with references updated.
5. **Merge the enforcement files.** The hook kit is NOT copied in: it is
   installed once per machine and covers every repository on it (changed
   2026-09-09). Git does not stack hook paths, so a project pointing at its
   own copy REPLACES the machine kit and opts itself out of the protection.
   Validate the shared kit before clearing a stale local `core.hooksPath`.
   Copy `scripts/validate.py` (a shim over the machine kit) and
   `scripts/bootstrap.sh`. Copy `RETROFIT.md` unchanged; the checker compares
   it with this canonical brief so future drift is visible. Merge
   `.editorconfig`. Build THIS project's `scripts/validate.config.json`:
   markdown allowlist, growable naming patterns, top-level directory lock,
   ignored generated/dependency files and word budgets. Preserve existing
   validation commands. Merge the template's `gitignore` entries into
   `.gitignore`, including `.claude/hooks-state/`.
6. **Verify each client separately.** Agent and Git gates have separate wiring.
   Read the admin client manifests and machine acceptance records. A global
   Git path proves nothing about Claude, Codex or Cursor events. Do not copy
   hooks into project settings or reinstall agent configuration during a
   routine retrofit. Missing machine wiring goes to admin installation work.
7. **Activate and validate.** From the target, run `sh scripts/bootstrap.sh`
   in Git Bash (or a Unix shell). It clears any stale per-project
   `core.hooksPath`, may rename master to main, and REFUSES to finish if no
   machine kit is installed - a project with no kit is ungated, so that is a
   failure, not a warning. Run `<python> scripts/validate.py` (a shim onto the
   installed kit) and the project's own checks, then stage the intended files
   and run `<python> scripts/validate.py --index` for staged structure checks.
   This is not the complete commit gate. Complete CONVENTIONS.md's code
   enforcement acceptance using the actual compiler, linter and test entry point. Resolve errors before committing.
8. **Prove enforcement.** In a disposable copy of the migrated target, commit
   the baseline cleanly, then confirm real commits reject an unlisted markdown
   file, a generated synthetic credential and private conversation attribution.
   Confirm a commit body and personal identity email are rejected, then push a
   synthetic two-commit branch where a credential is introduced and deleted;
   pre-push must still reject the earlier commit. Start the selected agent host in the target
   and record which configured events actually fire. Claude ConfigChange blocks
   a runtime reload after a disk edit; it cannot prevent that edit and the PC host
   tested so far hides its reason. Restore any probe changes. A parseable agent
   file is not proof that its specialist works.
9. **Audit and report. The retrofit is not done until the checker says so.**
   Run, from `_projects-admin`:

   ```bash
   <python> scripts/retrofit-check.py --project <project> --rules
   ```

   Read the report. Fix every gap or record a justified exception; otherwise
   the retrofit is unfinished.

   Preserve mature rules AND merge house defaults: autonomy, read list and
   scaffolding. State conflicts explicitly; project rules win. The 2026-09-20
   howe-creative incident showed that copying documents alone misses these.

   Re-run the explicit-target checker and record justified
   exceptions. An independent agent applies `STANDARDS-AUDIT.md`; fix findings and
   have the fixes re-audited. Commit and push under the declared Git policy:
   product L0/L1 merges its branch to main without asking; L2+ and creative
   defaults push the feature branch. Report the diff,
   test evidence, untested host events and remaining decisions. Stop at the
   review milestone; L2+ and creative defaults require approval before main.

## Updates after initial retrofit

Apply an approved admin update as a selective migration, not a fresh template
copy. From the project, an agent runs:

```bash
<python> "<repos>/_projects-admin/scripts/retrofit-check.py" --project .
```

It reads active CLAUDE.md, ENGINEERING.md and CONVENTIONS.md and reports
missing, current or drifted rules with canonical content hashes. Whitespace is
normalised; headings, partial text and old wording cannot pass as current.
Canonical coverage is not a conflict audit: independently read local overrides.
All checks are read-only by default, including explicit-target checks.

For an authorised target, `--project . --apply-rules` inserts only wholly
absent rules. Drift requires an explicit reviewed merge, not a second copy;
custom rules are never overwritten. Record justified exceptions. Replace the
brief and unmodified shims explicitly from the chosen kit after reviewing their
diffs; the checker no longer refreshes them implicitly. Re-run to verify hashes
and file equality. Templates declare their kind; a missing LEVELS.md does not
make an existing project creative. No multi-project apply is permitted.

Read the source commit, affected files, applicability and acceptance
criteria. Preserve project-specific rules and active work. Straightforward
rules/doc changes can be applied during the authorised review; implementation
work uses the existing handoffs/TEMPLATE.md and a ROADMAP entry so it is read.
A handoff's existence is not completion or new permission to merge main.

Record the update ID, source kit commit, affected files, tests, independent
review and resulting project commit in existing project records. Only advance
the recorded baseline when all applicable changes are verified; a partial
update lists the outstanding items. No-op/rejected items need a reason.

## CI and publication review

**Free-only resource policy:** follow `_projects-admin/RULES.md` section 2.14
and import `ci-free-tier-policy` from the standard-rules manifest. Run the
shared `hooks/ci_policy.py --audit` from the target repository to inventory its
HEAD workflows before editing; this is read-only, not retrofit authority.
Consolidate publication and app checks within 10 combined job-timeout minutes
across all workflows. Preserve existing protections and required checks.
Validate YAML with actionlint locally and the actual staged policy gate, not
just working files. Keep heavy local test evidence and a failure-propagating
project test entry point; do not install local hooks. Record measured runtime,
expected monthly run frequency, dated shared headroom and the zero-paid-budget
setting in existing decisions. The planning target is 1,600 shared minutes,
with 400 reserved, not a separate allowance for each repository.

Before claiming installation, verify the installed Git launcher passes
`ci_policy.py --check-runtime` and includes hook 30. Missing runtime is an
admin installation issue, not permission to skip validation. A Git-only update
must preserve agent trust. Prove clean and costly-workflow cases through real
foreign-repo commits/pushes, including prohibited intermediate commits, on each
machine. Do not claim Windows acceptance from Mac tests.

Apply the CI budget, push, false-positive and copy-check rules from
`scripts/standard-rules.json` to both new and existing projects. This is not
permission to retrofit other repositories or install per-project hook copies.

Inventory workflows and disabled state. Record account-wide usage, storage and
stop-usage settings before expansion; unreadable billing means unverified headroom.

Keep a lightweight automatic publication check for PRs to main and main
pushes. The product workflow is the reference: Linux, read-only permissions,
five-minute timeout, superseded-PR cancellation only. Do not exclude markdown
from publication scans. Scope application tests by relevant paths separately.
Keep browser, mutation and matrix work local. Nonstandard hosted triggers need
review under section 2.14, not routine retrofit authority. A skipped
required check must not strand a merge or masquerade as passing. Preserve
mandatory local validation, initial branch backup and each main push's scanned
commit range. No permanent CI shutdown as a cost-control default.

Record actual checks, disabled jobs and reactivation ownership. Timeouts do not
guarantee allowance; alerts do not stop usage. No billing or protection changes
without authority.

Keep reviewed public-address exceptions exact; do not whitelist an entire
domain or every dotted string. Do not rename code merely to appease a scanner.
Implement project-specific copy tests for rendered punctuation and shipped
data only where the project's declared rules require them. Preserve creative
assets; there is no blanket media ban.

## Vercel build policy

For new projects and authorised retrofits using Vercel only:

Otherwise record N/A; never create/connect/deploy a Vercel project to satisfy
this template.

1. Identify each connected project's configured root directory and effective
   config, including monorepos. Verify production is main; a different live
   branch needs a migration decision. Stop for unclear config precedence.
2. Copy missing `scripts/vercel-main-only.json` from the chosen template.
   **Replace** `git.deploymentEnabled` in the consumed `vercel.json` with
   `{"**": false, "main": true}`, preserving unrelated settings. Old true
   patterns reopen builds. For `vercel.ts` or another format, validate the
   equivalent there; never create competing configs. The preset alone is inert.
3. Carry the policy onto every active branch before its next push. Main's
   config alone does not protect older branches. Preserve the Git workflow.
4. Preview exceptions require Stephen's explicit project/branch request.
   Add only that literal name with true; retain deny-all. Use letters, digits,
   slash, dot, hyphen and underscore; other minimatch syntax needs review.
   Record purpose/retirement in DECISIONS.md. Remove exceptions from main and
   surviving branches when finished, including merges. Renewals need a request.
5. Inventory CI, dashboard, CLI/API and deploy hooks: separate deployment routes
   outside this Git setting. No bypass, duplicate routes or paid capacity.
   Routine local previews use the shared controller.
6. Record consumed path, map and production setting. At authorised pushes,
   observe main building, ordinary/slash branches not building, and requested
   previews only while enabled. No extra test deployments. Until observed,
   report configuration checks separately from hosted acceptance.

[Vercel reference](https://vercel.com/docs/project-configuration/git-configuration).
This controls automatic Git deployments, not account spending or local Git.

## Preview controller acceptance

For a new project or retrofit with a browser preview, inspect its current
working command, checkout and local/Tailscale addresses before changing them.
Keep those addresses. Registration is an explicit admin change to the machine's
existing switchboard registry, not automatic port allocation or a project hook.
The registry rejects duplicate local ports and public origins, including the
dashboard's own ports. Configure frameworks to fail on an occupied port (for
Vite, retain `--strictPort`); never enable fallback to the next free port.

Use `<python> "<repos>/_projects-admin/scripts/project_control.py" status`, then
`start` or `stop`, from the registered checkout or with its project ID appended.
Do not run an independent preview when the controller is unavailable. Confirm
that starting twice keeps one server, the dashboard can stop a CLI-started
server, the CLI can stop a dashboard-started server, and the same Tailscale link
opens after restart. Test a port conflict without killing an unrelated process.
Record the actual installed hook release and active host events. Machines with
no companion registry are explicitly not enforced yet; do not claim otherwise.
Do not enable enforcement there until its controller is installed and accepted.

## Credentials and boundaries

Inspect `.env` arrangements without printing values. Where Stephen has authorised
local/test equivalents, document the substitution; list anything requiring live
key changes for him. Never move or rewrite live credentials unasked.

Do not force-push, discard dirty work, delete or overwrite without listing the
changes, or expand to another project without authorisation. An external agent
coordinates this procedure; it does not justify a blind bulk copy.
