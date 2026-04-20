# AI Game Bug Triage: Project Summary

## 1. One-line summary

This project is an AI-assisted QA workflow tool for game teams that helps intake bugs, triage them, generate regression test candidates, and produce detailed grouped testcase plans from bug context plus supporting artifacts such as screenshots, PDFs, and notes.

## 2. What problem this solves

- Game QA and engineering teams often receive bugs from multiple places with inconsistent detail.
- Triage takes time because severity, ownership, and duplicate risk are usually decided manually.
- Fixes are often shipped without adding durable regression coverage.
- Test design is usually scattered across bug trackers, screenshots, spreadsheets, and design documents.
- This tool brings those steps into one workflow so a team can go from bug intake to AI-assisted triage to test generation inside one dashboard.

## 3. Product scope

- The product is intentionally limited to `mobile`, `pc`, and `console` games only.
- The prompts, heuristics, seeded examples, UI copy, and generated outputs are game-specific.
- It is designed around common game QA problem spaces such as:
  - gameplay issues
  - UI / UX issues
  - rendering defects
  - performance regressions
  - networking and matchmaking problems
  - platform compliance issues
  - save and progression bugs
  - commerce / live ops defects
  - build and release issues
  - audio issues

## 4. What is implemented today

- A Python backend built with FastAPI.
- A browser-based dashboard served directly by the backend.
- SQLite persistence for bugs, triage outputs, generated tests, uploaded artifacts, and generated test plans.
- AI-assisted bug triage with:
  - severity
  - priority
  - component classification
  - owner routing
  - duplicate hint
  - confidence score
  - evidence list
  - next action
- Regression test candidate generation for Unity, Unreal, and generic/custom harnesses.
- Intelligent testcase generation that accepts:
  - bug context
  - screenshots and images
  - PDFs
  - text notes
  - design documentation
- Grouped testcase plans with suites such as:
  - Smoke
  - Sanity
  - Regression
  - Functional
  - Non-functional
- Game-only showcase seed data so the product can be demonstrated immediately.

## 5. Core user workflows

### Workflow A: Bug Triage

1. A QA user creates a new game bug from the dashboard.
2. The bug is stored in SQLite as a normalized bug record.
3. The issue appears in the queue with searchable and filterable metadata.
4. The user runs triage.
5. The system analyzes the bug using either:
   - OpenAI, if `OPENAI_API_KEY` is configured, or
   - the local heuristic fallback, if the key is absent or the API fails.
6. The UI shows the triage summary, severity, component, owner team, duplicate candidate, confidence, evidence, and recommended next action.
7. The bug record is updated with the triage classification.

### Workflow B: Regression Test Generation

1. A triaged bug is selected.
2. The user clicks `Generate regression test`.
3. The backend chooses an engine-aligned framework:
   - Unity -> `Unity Test Framework`
   - Unreal -> `Unreal Automation Spec`
   - other/custom -> `Pytest Harness`
4. A candidate test file is generated and written into `generated_tests/`.
5. The file path, framework, execution summary, and generated code are shown in the dashboard.

### Workflow C: Intelligent Test Design

1. The user switches to `Test Design Studio`.
2. The user selects a bug from the bug library.
3. The user adds:
   - feature goal
   - design notes
   - focus areas
   - screenshots, PDFs, and text artifacts
4. The backend stores the artifacts in `artifacts/bug_<id>/`.
5. The system generates a detailed test plan using either the LLM path or the heuristic fallback.
6. The resulting plan is stored in SQLite and rendered as grouped suites with detailed testcases.

## 6. How I would explain the architecture in an interview

### High-level architecture

- `Frontend dashboard`
  - HTML, CSS, and JavaScript served by FastAPI
  - gives two main work modes:
    - `Bug Triage`
    - `Test Design Studio`
- `API layer`
  - receives UI actions and exposes JSON endpoints
  - returns dashboard metrics, bug lists, and detailed bug views
- `Service layer`
  - triage service
  - regression test generation service
  - intelligent test design service
  - OpenAI integration service
- `Persistence layer`
  - SQLite repository for durable records
- `Filesystem outputs`
  - generated regression tests written to `generated_tests/`
  - uploaded and derived artifacts written to `artifacts/`

### Why this architecture is good for an MVP

- It keeps deployment simple: one Python app, one database, one dashboard.
- It makes the product easy to demo locally.
- It isolates the AI logic behind service interfaces, so heuristics and live LLM calls use the same workflows.
- It is extensible: Jira, GitHub, Sentry, auth, CI execution, and vector retrieval can be added later without redesigning the whole app.

## 7. Backend design

### Application entrypoint

- `src/bug_triage/app.py`
- This file wires together:
  - settings
  - repository
  - triage service
  - regression test generation service
  - intelligent test design service
  - FastAPI routes
- On startup it also initializes the database and seeds demo data.

### Configuration

- `src/bug_triage/config.py`
- Main runtime settings:
  - database path
  - generated tests folder
  - artifact storage folder
  - AI mode
  - OpenAI models
- Supported AI modes:
  - `auto`
  - `openai`
  - `heuristic`

### Repository layer

- `src/bug_triage/repository.py`
- This is the data access layer.
- It creates and manages the following tables:
  - `bugs`
  - `triage_recommendations`
  - `test_candidates`
  - `test_design_artifacts`
  - `generated_test_plans`
- It also provides dashboard metrics, bug listing, latest triage retrieval, test candidate retrieval, artifact retrieval, and test plan retrieval.

### Data models

- `src/bug_triage/models.py`
- Main entities:
  - `BugRecord`
  - `TriageRecommendation`
  - `TestCandidate`
  - `TestDesignArtifact`
  - `GeneratedTestPlan`

### Request schemas

- `src/bug_triage/schemas.py`
- Pydantic models validate:
  - bug creation input
  - test design artifact input
  - intelligent testcase plan input
- This ensures the product only accepts game-scoped platforms: `mobile`, `pc`, `console`.

## 8. AI and decisioning design

### Triage service

- `src/bug_triage/services/triage.py`
- This service converts a bug into a structured triage recommendation.
- It handles:
  - severity inference
  - component inference
  - owner-team mapping
  - duplicate detection
  - root-cause hinting
  - next-action recommendation
- The heuristic mode works using:
  - game-domain keyword matching
  - component keyword matching
  - duplicate scoring with `SequenceMatcher`
  - game-specific owner mapping

### Regression test generation service

- `src/bug_triage/services/testgen.py`
- This service creates a candidate automated regression test.
- It decides:
  - what kind of regression test to generate
  - which framework to use
  - what file extension to use
  - what starter code to emit
- It writes the generated output to disk so the demo shows a real artifact, not just text in memory.

### Intelligent testcase generation service

- `src/bug_triage/services/testplan.py`
- This service creates grouped QA plans with detailed cases.
- It also ingests artifacts and stores them per bug.
- The heuristic version still produces high-structure output with:
  - assumptions
  - suite grouping
  - coverage focus
  - detailed steps
  - expected results
  - edge cases
  - automation notes

### OpenAI integration

- `src/bug_triage/services/llm.py`
- This is the real LLM integration layer.
- It uses OpenAI structured outputs for:
  - triage
  - regression test generation
  - intelligent test plan generation
- It keeps strong structure using Pydantic response models.
- If OpenAI is unavailable, the calling services fall back to heuristic mode.

## 9. Frontend and UX design

### Dashboard purpose

- The dashboard is meant to feel like a QA command center rather than a prototype form page.
- It separates fast operational triage from deeper authored test design.

### Main UI sections

- top status header
- KPI metrics strip
- workspace mode switcher
- bug intake form
- issue queue
- bug review panel
- regression candidate panel
- test design studio
- artifact review area
- grouped testcase plan area

### Frontend implementation

- `src/bug_triage/templates/dashboard.html`
- `src/bug_triage/static/styles.css`
- `src/bug_triage/static/app.js`

### How the frontend works

- The page loads once from FastAPI.
- JavaScript fetches:
  - `/api/health`
  - `/api/dashboard`
- The dashboard then hydrates:
  - metrics
  - queue cards
  - selected bug detail
  - triage view
  - regression test view
  - artifact list
  - test plan view
- The UI supports live actions without page reload for:
  - bug creation
  - triage generation
  - regression test generation
  - intelligent testcase generation

## 10. API design

### Main routes

- `GET /`
  - serves the dashboard
- `GET /api/health`
  - returns runtime status and current execution mode
- `GET /api/dashboard`
  - returns metrics plus summarized bug list
- `POST /api/bugs`
  - creates a new bug
- `GET /api/bugs/{bug_id}`
  - returns full bug detail
- `POST /api/bugs/{bug_id}/triage`
  - runs AI-assisted triage
- `POST /api/bugs/{bug_id}/generate-tests`
  - creates a regression candidate
- `POST /api/bugs/{bug_id}/generate-intelligent-testcases`
  - ingests artifacts and generates grouped testcase suites

## 11. Demo data and interview demonstration value

### Why the demo seed matters

- A demo product is stronger when every major feature can be shown immediately.
- The seed service guarantees that the dashboard starts with realistic game-based examples instead of empty states.

### What is seeded

- console suspend / resume hard-lock example
- mobile matchmaking failure example
- PC ultrawide UI overlap example
- mobile reward claim soft-lock example
- PC input / photo mode freeze example

### Why this is useful in a demo

- One bug shows triage.
- Another shows regression test generation.
- Another shows artifact-backed testcase planning.
- Together they demonstrate the entire workflow end-to-end.

## 12. End-to-end flow in simple interview language

If I were demoing this in an interview, I would explain it like this:

1. I start on the dashboard and show that the tool is focused only on game QA for mobile, PC, and console.
2. I create a new bug with game title, platform, engine, build, description, and optional stack trace.
3. The bug appears immediately in the issue queue and updates the top-level metrics.
4. I open the bug and run triage.
5. The system either calls OpenAI or falls back to its game-domain heuristic engine.
6. The triage result comes back with severity, priority, owner, component, confidence, evidence, and next action.
7. I then generate a regression test candidate, and the tool writes a real file to disk and shows the generated code in the UI.
8. Next, I switch to `Test Design Studio`.
9. I attach screenshots or design notes and ask the tool to generate detailed suites.
10. The system stores the artifacts, analyzes the bug context plus the uploaded material, and returns grouped testcases for Smoke, Sanity, Regression, Functional, and Non-functional coverage.
11. That demonstrates that the system is not just summarizing bugs, but turning them into QA execution assets.

## 13. Current strengths

- Strongly scoped product definition for game teams only.
- Clean separation between backend, services, repository, and frontend.
- Real LLM path is already integrated.
- Useful heuristic fallback makes the tool demoable without API keys.
- Durable outputs are created on disk and in the database.
- Showcase seed data makes the full workflow visible immediately.
- The dashboard now has separate operational modes for triage and test design.

## 14. Current limitations

- Generated regression tests are starter candidates, not repository-aware executable tests.
- There is no source-code retrieval, blame lookup, or commit context yet.
- There is no real external connector yet for Jira, GitHub, Sentry, or Crashlytics.
- There is no authentication, RBAC, audit trail UI, or multi-user workflow yet.
- Test execution is not connected to CI yet; candidates are generated and stored, but not run automatically.
- The product is still a local MVP rather than a production-deployed SaaS platform.

## 15. What I would build next

- repository-aware retrieval so generated tests align with the real game codebase
- GitHub, Jira, and crash-report connectors
- CI execution hooks for generated tests
- richer duplicate clustering using embeddings and historical resolution data
- device / platform coverage matrix support
- reviewer actions such as accept, reject, edit, and export
- model evaluation and feedback capture for triage quality
- authentication and multi-user collaboration

## 16. Key files to mention in an interview

- `src/bug_triage/app.py`
- `src/bug_triage/config.py`
- `src/bug_triage/repository.py`
- `src/bug_triage/models.py`
- `src/bug_triage/schemas.py`
- `src/bug_triage/services/triage.py`
- `src/bug_triage/services/testgen.py`
- `src/bug_triage/services/testplan.py`
- `src/bug_triage/services/llm.py`
- `src/bug_triage/services/seed.py`
- `src/bug_triage/templates/dashboard.html`
- `src/bug_triage/static/app.js`
- `src/bug_triage/static/styles.css`

## 17. Final interview takeaway

The strongest way to present this project is:

- It is not just a UI prototype.
- It is not just an LLM wrapper.
- It is a working end-to-end QA workflow MVP for games.
- It accepts real bug input, stores it, analyzes it, generates structured triage, creates regression artifacts, ingests supporting documents, and turns all of that into actionable testcase suites inside a single dashboard.
