# Release Workflow

1. Review `PROJECT_STATE.md`, open issues, migrations and release scope.
2. Run the full relevant automated test suite, lint/type checks and production build.
3. Verify configuration and secrets handling; never include credentials in the release.
4. Verify provider/data licensing and clearly document external dependencies.
5. Verify stale-data safeguards, monitoring recovery, notification behaviour and model rollback.
6. Verify paper-trading/backtest reports are reproducible and labelled correctly.
7. Document known limitations and unsupported functionality.
8. Produce deployment, startup, monitoring and recovery instructions.
9. Update version and project state only after checks pass.
10. Never claim profitability, accuracy, regulatory approval or production readiness without evidence.
