# Overcall web app

The frontend is a React and TypeScript app built with Vite. It can be started locally without a
backend for the public landing page.

## Run locally

```sh
npm install
npm run dev
```

Copy `.env.example` to `.env.local` only when you need to configure local service URLs or Supabase.
Values prefixed with `VITE_` are included in the browser build; do not put secrets in them.

## Checks

```sh
npm test
npm run check:design
npm run build
npm run test:e2e
```

The landing page uses local fonts and static preview data. Its content does not call the backend.
