# AGENTS: Protocol for This Repository

## Purpose
This file is the persistent operating protocol for AI/code agents working in this repository.
Primary goal: avoid repeated regressions and loss of context between sessions.

## Mandatory Read Order Before Any Code Change
1. `docs/TASK_STATE.md`
2. `docs/DECISIONS.md`
3. `docs/KNOWN_ISSUES.md`
4. `docs/DEV_LOG.md` (latest entries first)
5. `docs/PROJECT_OVERVIEW.md` (полная документация по проекту)
6. Current task file (`task.md` when present)

If instructions conflict, do not guess. Stop and ask the user for a decision.

## Non-Negotiable Guardrails
- Keep stack unchanged unless user explicitly approves extension:
  - Django 5.2 LTS, Python 3.13, Redis, Celery, PostgreSQL, Docker, DaisyUI + Tailwind CSS, Alpine.js, Font Awesome
- Do not remove production data without explicit user approval.
- **Docker-only development.** NEVER install packages on the host machine (no `brew install`, no `pip install`, no `npm install -g`, no local venv). All commands run through `docker compose exec` or `docker run --rm`. CSS builds: `docker run --rm -v "$(pwd)":/app -w /app node:18-alpine sh -c "npm install && npx tailwindcss ..."`.
- Do not introduce one-off hacks for symptoms. Fix root logic and all affected flows.

## Update Ritual (Required After Non-Trivial Changes)
After each meaningful code change:
1. Add/update decision in `docs/DECISIONS.md` if behavior/invariant changed.
2. Update `docs/TASK_STATE.md` (done/in progress/blocked).
3. Add concise entry to `docs/DEV_LOG.md` with date, files, validation, risks.
4. If a known bug is discovered or closed, update `docs/KNOWN_ISSUES.md`.
5. If the change is visible to end users (UI, behavior, removed/added features), add entry to `docs/RELEASE_NOTES.md`:
   - Language: Russian.
   - No technical details (no file names, model names, API internals).
   - Group by date (newest first), then by section: «Новое», «Улучшения», «Исправления».
   - One sentence per item, from the user's perspective.

## Validation Baseline (Docker)
Unless task says otherwise, use:
1. `docker compose down`
2. `docker compose up -d --build`
3. `docker compose run --rm web python manage.py check`
4. Targeted tests for changed modules
5. Manual HTTP render check for affected pages

If any step fails, fix and rerun. Partial validation is not considered done.

