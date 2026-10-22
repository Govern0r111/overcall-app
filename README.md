# Here are your Instructions
# Overcall

Overcall monitors API traffic, detects wasteful usage patterns, and estimates savings.

## Deployment

- **Frontend:** deploy the `frontend` directory to Vercel.
- **Backend:** deploy the `backend` service to Render using the included `render.yaml`.
- **Database and auth:** create a Supabase project, run `supabase/migrations/20261021140000_initial.sql` in the Supabase SQL editor, then configure the environment variables from `frontend/.env.example` and `backend/.env.example`.

Never expose `SUPABASE_SERVICE_ROLE_KEY` in the frontend or commit real environment files.
