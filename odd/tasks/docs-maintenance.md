# Feature: docs-maintenance — doc accuracy fixes + maintainer-facing docs

Parent: user batch 2026-10-04 (item: "Fixes + docs de mantenedor").

## Purpose

Close the documentation-audit findings: stale test counts in
`docs/DEVELOPMENT-TOOLS.md` (said 6/6, suite is 32), the old "11 secciones"
reference, and the missing maintainer-facing content for the upcoming
GitHub remote (no contribution guide, no changelog, no versioning notes).

## Tasks

| ID | Title | Status | Note |
|---|---|---|---|
| 1 | DEVELOPMENT-TOOLS.md accuracy fixes | done | 6/6 → 32/32 with suite inventory; 11 → 12 secciones; footer updated |
| 2 | CONTRIBUTING.md | done | setup, checks, workflow, maintenance policy (versioning, issues, secrets, docs accuracy, firmware conventions), bug-report template |
| 3 | CHANGELOG.md | done | Keep-a-Changelog format; Unreleased history reconstructed from git log (viewer, hardening, body-position, review fixes, initial pipeline) |
| 4 | Native review (RDD on) of the committed range | done | Lineage review-c33ce6305ce0bce5: tier low, non_executable_only, ZERO lenses, auto-approved at START; acknowledge-approved burned authority (revision sha256:54f7b66e…, evidence gentle-ai.review-acknowledged/v1) |

## Verification evidence

- Docs-only range 9aaf37b → 1059d9c (4 files, 141 lines): CONTRIBUTING.md, CHANGELOG.md, DEVELOPMENT-TOOLS.md fixes, this doc.
- Native review auto-approved (tier low, zero lenses) and authority burned; no correction consumed.
