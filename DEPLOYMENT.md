# MedTruth AI Deployment (Vercel + Render)

This setup deploys:
- Frontend (Next.js): Vercel
- Backend (FastAPI): Render

Suggested service names:
- Vercel project: `tejas-medtruth-app`
- Render web service: `tejas-medtruth-api`

---

## 1) Deploy Backend on Render

1. In Render, create **Web Service** from this GitHub repo.
2. Render detects `render.yaml` automatically.
3. Set required env vars in Render dashboard:
   - `ALLOWED_ORIGINS=https://tejas-medtruth-app.vercel.app`
   - `MONGO_URI=<your_mongo_atlas_uri>`
   - `MONGO_DB=medtruth_ai`
   - `ANTHROPIC_API_KEY=<...>`
   - `GROQ_API_KEY=<...>` (optional)
   - `GEMINI_API_KEY=<...>` (optional)
   - `NCBI_API_KEY=<...>` (optional)
4. Deploy and copy backend URL, for example:
   - `https://tejas-medtruth-api.onrender.com`

Health check:
- `https://tejas-medtruth-api.onrender.com/health`

---

## 2) Deploy Frontend on Vercel

1. In Vercel, import the same GitHub repo.
2. Set **Root Directory** to `frontend`.
3. Add env vars:
   - `NEXT_PUBLIC_API_URL=https://tejas-medtruth-api.onrender.com/api/v1`
   - `NEXTAUTH_URL=https://tejas-medtruth-app.vercel.app`
   - `NEXTAUTH_SECRET=<long_random_secret>`
   - `GOOGLE_CLIENT_ID=<...>`
   - `GOOGLE_CLIENT_SECRET=<...>`
4. Deploy.

---

## 3) Final CORS update

After frontend deploy, update backend env var on Render:

- `ALLOWED_ORIGINS=https://tejas-medtruth-app.vercel.app`

If you add custom domains later, include both:
- `ALLOWED_ORIGINS=https://app.tejasmedtruth.ai,https://tejas-medtruth-app.vercel.app`

---

## 4) Optional custom domains

- Frontend: `app.tejasmedtruth.ai` -> Vercel project
- Backend: `api.tejasmedtruth.ai` -> Render service

Then update:
- `NEXTAUTH_URL=https://app.tejasmedtruth.ai`
- `NEXT_PUBLIC_API_URL=https://api.tejasmedtruth.ai/api/v1`
- `ALLOWED_ORIGINS=https://app.tejasmedtruth.ai,https://tejas-medtruth-app.vercel.app`

