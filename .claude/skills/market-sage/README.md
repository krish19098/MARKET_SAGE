# MARKET SAGE Skill Package

This package contains a reusable Claude Skill and modular project references.

## Install
1. Upload `market-sage-skill.zip` as a custom Skill in Claude's Skills settings.
2. Enable the Skill.
3. In your application repository, create `PROJECT_STATE.md` from `templates/PROJECT_STATE_TEMPLATE.md`.
4. Start a Claude coding session with: "Use the MARKET SAGE skill. Inspect this repository and PROJECT_STATE.md, then continue from the highest-priority incomplete milestone. Do not assume planned features are implemented."

## Contents
- `SKILL.md`: concise entry point and routing rules.
- `references/`: complete product and engineering requirements.
- `workflows/`: repeatable build, research, debug and release procedures.
- `templates/PROJECT_STATE_TEMPLATE.md`: persistent repository progress record.

The Skill reduces the need to paste the entire brief repeatedly. It does not make loaded instructions token-free; Claude may load relevant reference files when a task requires them.
