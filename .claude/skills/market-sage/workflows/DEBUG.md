# Debug Workflow

1. Reproduce the issue and capture exact error, timestamp, environment and affected version.
2. Inspect the smallest relevant code path and dependencies.
3. Check data freshness, provider status, timezone, symbol mapping and missing inputs where relevant.
4. Form a testable root-cause hypothesis.
5. Make a minimal scoped change; do not refactor unrelated code.
6. Add a regression test.
7. Run focused tests, then broader tests/build as appropriate.
8. Verify no original prediction records or audit history were modified.
9. Record root cause, fix, tests and remaining risk in `PROJECT_STATE.md`.
10. Do not claim resolution until the failure is reproduced as fixed.
