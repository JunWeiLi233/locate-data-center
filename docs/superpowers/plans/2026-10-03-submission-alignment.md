# Hackathon Submission Alignment Implementation Plan

> **For agentic workers:** Execute the bounded backend and frontend tasks with independent ownership and review. Preserve all existing working-tree changes and accepted run evidence.

**Goal:** Turn verified saved model outputs into the six requested submission deliverables, and document the remaining scientific gaps against all five rubric categories.

**Architecture:** Add a read-only saved-run brief builder and a new `submission` CLI command. It verifies archived output hashes, selects representatives using stored ranks within one scenario, presents stored weights/contributions and paired physical quantities, and writes a fresh JSON/Markdown/printable HTML package. The frontend renders the same backend brief. Existing model mathematics, source data, weights and accepted outputs remain the source of decisions. New presentation code constitutes an additive delivery revision, not renewed validation of archived science.

**Tech Stack:** Python 3.12, pandas/PyArrow, existing model IO; React/TypeScript and the existing local API.

## Design and scope decision

The user's instruction to audit and continue development authorizes reversible implementation. Options considered: change scoring to reward unsupported ecosystem factors; write static claims by hand; generate a traceable brief from archived outputs. The last option addresses demonstrable presentation gaps while keeping unsupported quantities null. Heat reuse and community/material plans are explicitly proposed investigation work, with no invented recovery coefficient, supplier, jobs, price, or carbon offset. DOE/FEMP 2024 guide, section 7.1 (printed page 28), supports heat-host, temperature-match and backup-rejection checks; it provides no coefficient used by this revision.

## Task 1: Verified backend submission builder (root ownership)

Files: create `src/dc_locator/submission.py`, `src/dc_locator/submission_rendering.py`, `tests/test_submission.py`; add command wiring in `src/dc_locator/cli.py`.

Additive mission gap: create `src/dc_locator/model/heat_reuse.py`, `tests/test_heat_reuse.py` and an all-null heat-host input template. The optional alternative-bound input contract requires a basis/rationale or documented factor reference and section. Delivered heat is demand-capped, distribution losses are explicit, and auxiliary electricity emissions reduce the separate heating-system comparison. Missing values remain null and no result is credited against MCDA or facility emissions.

- [x] Test first: missing module must fail the new command/function tests. Hand-check same-cell water delta: tower `210240 m3/year` minus dry `0 m3/year` is `210240 m3/year`; missing electricity water stays null and cannot imply total-water savings. Use in-memory alternatives and an explicitly synthetic test run, never invented real evidence.
- [x] Verify saved-run required output hashes, table data modes/grid identities, completed stages and unique alternative keys. Reject corrupt, partial, ambiguous-scenario and already occupied output paths before writing. No source-run mutation.
- [x] Build six deliverables with stored region representatives, exact criterion weights/contributions, physical statuses/confidences, provenance/coverage, source/config/code identity, screening risk actions, and a proposed opening-through-final-operating-year roadmap.
- [x] Render deterministic JSON/Markdown/HTML (escaped content, print styles), with no fabricated geographic labels or national-optimum claim. Keep construction, useful heat, electricity-generation water, workforce, economics and full lifecycle unknown unless supported by matching artifacts.
- [x] Run targeted submission, heat-reuse and CLI tests, then the full suite recorded below.

## Task 2: Decision explanation and printable UI (frontend worker ownership)

Files: frontend serialization/API/domain/parser and related tests; new `DecisionBrief.tsx`; bounded `App.tsx`/styles integration.

- [x] Transport the read-only backend brief as an optional API field, with unavailable fallback for older/incomplete evidence and cache identity covering every consumed artifact. Keep original saved-run compatibility.
- [x] Populate actual strengths from recorded criterion contributions with their proxy limitations; do not invent advantages or recalculate scores in the browser.
- [x] Render six sections and a printable dialog, including empty STRICT and synthetic modes, assumptions, UNKNOWN resource totals and a project-plan operating vision.
- [x] Run frontend unit suite, production build, and bridge tests.

## Task 3: Review, real package and handoff (root ownership)

- [x] Independent review of implementation and unknown/proxy boundaries; fix material findings.
- [x] Generate `runs/submission_alignment_v1/` draft and final `runs/submission_alignment_v2/` from `runs/national_discovery_v2/`; independently verify persisted recommendation and every consumed/output hash. Accepted science remains unchanged.
- [x] Write `docs/submission_alignment.md` mapping every mission factor, six deliverables and five rubric categories to evidence and remaining limits. Add a concise live-demo/pitch script.
- [x] Run full project/bridge tests and frontend tests/build. Inspect printable HTML and real frontend presentation.
- [x] Record commands, counts, hashes, scope and remaining acquisition/engineering blockers in handoff, `docs/phase_records/phase_10.json`, and run index. Cleanup is the final workspace operation.

## Completion evidence

Independent review: GO. Full Python/API suite: 633 passed in 100.96 seconds. Root frontend suite:
98 passed in 12.86 seconds; production build passed with the existing bundle-size advisory. Final audit
verified 13 consumed inputs, three report outputs and three presentation-code hashes; all 68 recorded
national exploratory/STRICT output hashes remain unchanged. Real browser inspection confirmed the
printable report and all six frontend sections. Exact scope, implementation hashes and remaining scientific
gaps are recorded under `runs/submission_alignment_v2/`. Parallel regional refinement is not accepted here.
