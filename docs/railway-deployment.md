# Railway Deployment

This project deploys to Railway as a single web service backed by one attached persistent volume.

## What is included

- `Dockerfile`: deterministic Python 3.11 image build
- `railway.json`: Railway build and deploy settings
- volume-aware runtime config: SQLite, generated tests, and uploaded artifacts automatically move onto the Railway volume when `RAILWAY_VOLUME_MOUNT_PATH` is present
- `.env.example`: variables you can copy into Railway

## Railway service layout

- Service type: web service
- Persistent storage: one attached volume
- Volume mount path: `/data`

When the volume is mounted at `/data`, the app stores runtime data here:

- SQLite database: `/data/bug_triage.db`
- generated tests: `/data/generated_tests`
- uploaded artifacts: `/data/artifacts`

## Required Railway setup

1. Create a new Railway project and connect this repository.
2. Add one service from the repo root.
3. Attach a volume to that service.
4. Set the volume mount path to `/data`.
5. In the service variables, add:

```env
BUG_TRIAGE_AI_MODE=auto
BUG_TRIAGE_SEED=false
```

6. If you want live OpenAI-backed triage and test generation, also add:

```env
OPENAI_API_KEY=your_key_here
OPENAI_TRIAGE_MODEL=gpt-5-mini
OPENAI_TESTGEN_MODEL=gpt-5.2
```

7. Deploy the service.

## Runtime behavior

- Healthcheck path: `/api/health`
- Public UI route: `/`
- API base: `/api`
- Seeding defaults to `false` on Railway so production deploys do not keep injecting demo data

## Verify after deploy

1. Open the Railway public domain.
2. Confirm the dashboard loads.
3. Call `/api/health` and verify it returns `status: ok`.
4. Create a sample bug from the UI and confirm data survives a redeploy.

## Notes

- Railway automatically injects `PORT`; the container command uses it directly.
- If you mount the volume somewhere other than `/data`, the app still works because it auto-detects `RAILWAY_VOLUME_MOUNT_PATH`.
- If you want to force a custom storage layout, set `BUG_TRIAGE_STORAGE_ROOT` or the per-path overrides shown in `.env.example`.
