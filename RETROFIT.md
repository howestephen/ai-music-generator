---
status: active
author: stephen+claude
created: 2026-08-19
updated: 2026-09-09
note: "Canonical self-contained import and retrofit guidance for one authorised project."
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
files with a blind copy.

An external coordinating agent can perform existing-project work one project
at a time; Stephen does not need to open a separate session in every project.
Each target still needs its own inspection, branch, validation and independent
audit. Authorisation to work in the admin repos does not authorise changes
elsewhere.

Existing project rules record real incidents. Read them in full and preserve
them when merging the house defaults. Do not replace a mature project with a
template or turn a static checker result into a claim that every rule works.

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
`ai-standards` repo was folded in on 2026-09-09. The global bootstrap
(`scripts/bootstrap-house.<sh|ps1>`) is a separate, once-per-machine
installation; it does not retrofit a project's files.

## Procedure

1. **Record state and read local rules.** Report branch, dirty files and
   ahead/behind. Preserve existing work; use a fresh branch from current main.
   Record the source kit commit. Read the project's rule files and their required
   documents before proposing the exact changes. Push feature branches as backup;
   main needs Stephen's express permission for that instance.
2. **Check just this target.** Run
   `<python> "<repos>/_projects-admin/scripts/retrofit-check.py" --project "<project>"`.
   Keep the initial gap report. This is a static check of selected requirements;
   it cannot prove live hooks, global policy or every project-specific rule.
3. **Merge the rules.** Make CLAUDE.md authoritative, preserving real rules from
   AGENTS.md and leaving AGENTS.md a short pointer. Include autonomy, the necessary
   read list, independent audit before done, and a handoff/archiving convention.
   Bring over relevant template procedures, not unrelated product levels or
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
   If this project has a local `core.hooksPath`, clear it.
   Copy `scripts/validate.py` (a shim over the machine kit) and
   `scripts/bootstrap.sh`. Copy `RETROFIT.md` unchanged; the checker compares
   it with this canonical brief so future drift is visible. Merge
   `.editorconfig`. Build THIS project's `scripts/validate.config.json`:
   markdown allowlist, growable naming patterns, top-level directory lock,
   ignored generated/dependency files and word budgets. Preserve existing
   validation commands. Merge the template's `gitignore` entries into
   `.gitignore`, including `.claude/hooks-state/`.
6. **Agent wiring needs nothing per project.** The 14 agent hooks are installed
   into `~/.claude/settings.json` by
   `scripts/install_global_hooks.py --apply`, so they already fire in this
   project. Do not copy a hooks block into the project's own
   `.claude/settings.json`; per the hooks reference an identical handler
   defined in both runs once, but a divergent project copy is drift waiting to
   happen. Keep project settings for project-specific keys only.
7. **Activate and validate.** From the target, run `sh scripts/bootstrap.sh`
   in Git Bash (or a Unix shell). It clears any stale per-project
   `core.hooksPath`, may rename master to main, and REFUSES to finish if no
   machine kit is installed - a project with no kit is ungated, so that is a
   failure, not a warning. Run `<python> scripts/validate.py` (a shim onto the
   installed kit) and the project's own checks, then stage the intended files
   and run `<python> scripts/validate.py --index` to see exactly what the
   commit hook will see. Resolve errors before committing.
8. **Prove enforcement.** In a disposable copy of the migrated target, commit
   the baseline cleanly, then stage an unlisted markdown file and confirm a real
   commit is refused for the expected reason. Start the selected agent host in the target
   and record which configured events actually fire. Claude ConfigChange blocks
   a runtime reload after a disk edit; it cannot prevent that edit and the PC host
   tested so far hides its reason. Restore any probe changes. A parseable agent
   file is not proof that its specialist works.
9. **Audit and report.** Re-run the explicit-target checker and record justified
   exceptions. An independent agent applies `STANDARDS-AUDIT.md`; fix findings and
   have the fixes re-audited. Commit and push the target's feature branch after
   sign-off. Report the diff, test evidence, untested host events and remaining
   decisions. Stop at the review milestone before main is pushed.

## Credentials and boundaries

Inspect `.env` arrangements without printing values. Where Stephen has authorised
local/test equivalents, document the substitution; list anything requiring live
key changes for him. Never move or rewrite live credentials unasked.

Do not force-push, discard dirty work, delete or overwrite without listing the
changes, or expand to another project without authorisation. An external agent
coordinates this procedure; it does not justify a blind bulk copy.
