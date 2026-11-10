# Build Workflow

1. Inspect repository, branches, runtime, dependencies, tests, environment and current `PROJECT_STATE.md`.
2. Read `references/MASTER_SPECIFICATION.md` and only the domain references needed for the milestone.
3. Summarise the current architecture and identify the smallest vertical slice that can be completed safely.
4. Verify external provider documentation, credentials, data licensing and operational dependencies.
5. Implement the slice while preserving existing working code and conventions.
6. Add tests for normal, edge, failure and stale-data paths.
7. Run relevant tests, lint/type checks and production build.
8. Inspect logs and fix regressions.
9. Update `PROJECT_STATE.md` with actual changes, test results, blockers and next task.
10. Report what works, what is mocked, what needs credentials/subscription, and what remains.

Do not create an impressive but nonfunctional UI in place of core data and prediction functionality. Do not claim a milestone complete without evidence.
