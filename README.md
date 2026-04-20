# AI Game Bug Triage MVP

This repository contains the first executable slice of an AI-assisted bug triage and test generation platform for mobile, PC, and console games only.

## What is implemented

- FastAPI backend for game bug intake, triage, and candidate test generation
- SQLite persistence using the Python standard library
- Real OpenAI-backed LLM integration for triage and test generation when `OPENAI_API_KEY` is configured
- Heuristic fallback mode when the LLM is unavailable
- Browser dashboard served directly by the backend
- Artifact-backed intelligent testcase generation for game QA suites
- Game-only showcase seed data covering triage, regression generation, and intelligent testcase design
- Unit tests for heuristic logic and LLM service wiring

## Quick start

1. Install the dashboard dependencies with `python -m pip install --target .deps .`
2. Optionally set `OPENAI_API_KEY` to enable real LLM calls
3. Optionally set `BUG_TRIAGE_AI_MODE` to `openai`, `auto`, or `heuristic`
4. Run the app with `python run_dashboard.py`
5. Open `http://127.0.0.1:8000`

`BUG_TRIAGE_AI_MODE=auto` is the default. It uses OpenAI when an API key is present and falls back to heuristics otherwise.

## OpenAI configuration

- `OPENAI_API_KEY`: enables live LLM requests
- `OPENAI_TRIAGE_MODEL`: defaults to `gpt-5-mini`
- `OPENAI_TESTGEN_MODEL`: defaults to `gpt-5.2`
- `BUG_TRIAGE_AI_MODE`: `auto`, `openai`, or `heuristic`

## Railway deployment

Railway deployment files are included in the repo:

- `Dockerfile`
- `railway.json`
- `.env.example`
- `docs/railway-deployment.md`

For the deployment steps, required variables, and the persistent-volume setup for SQLite and artifacts, see `docs/railway-deployment.md`.

## Product scope

This tool is intentionally limited to game teams shipping on:

- mobile
- PC
- console

The intake schema, prompts, heuristics, and generated tests are biased toward gameplay, UI, rendering, performance, networking, platform-compliance, progression, live-ops, and build-release issues.

## Intelligent testcase generation

The dashboard now includes a dedicated section for generating detailed QA testcase suites from:

- game bug context
- screenshots and other images
- PDF design documents
- text-based notes or specs
- supplemental QA instructions and risk notes

The generated output is grouped into suites such as:

- Smoke
- Sanity
- Regression
- Functional
- Non-functional

Each testcase includes structured fields for objective, preconditions, steps, expected results, edge cases, tags, priority, and automation notes.

## Project layout

- `src/bug_triage/app.py`: FastAPI application and routes
- `src/bug_triage/repository.py`: SQLite data access and additive migrations
- `src/bug_triage/services/triage.py`: game-domain triage engine with LLM fallback
- `src/bug_triage/services/testgen.py`: game-domain test generation engine with LLM fallback
- `src/bug_triage/services/testplan.py`: intelligent grouped testcase generation service
- `src/bug_triage/services/llm.py`: OpenAI structured-output integration
- `src/bug_triage/templates/`: dashboard template
- `src/bug_triage/static/`: dashboard styles and client-side logic
- `tests/`: unit tests

## Current limitations

- There is no repository-aware code retrieval yet, so generated tests are engine-shaped candidates rather than codebase-grounded patches
- External connectors like Jira, GitHub, and Sentry are still mocked by local intake endpoints
- The live dashboard is still a single-node local prototype rather than a multi-user production deployment

The architecture document lives at `docs/ai-bug-triage-system-design.md`.
