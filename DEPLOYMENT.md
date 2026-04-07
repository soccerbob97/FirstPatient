# Deployment Guide - Render + Vercel

## Architecture

| Component | Platform | Cost |
|-----------|----------|------|
| **Backend** (FastAPI) | Render | $7/mo (Starter plan) |
| **Frontend** (React) | Vercel | Free |
| **Database** | Supabase | Free tier / $25/mo |

---

## Backend Deployment (Render)

### 1. Create Render Account

1. Go to [render.com](https://render.com)
2. Sign up with GitHub

### 2. Create New Web Service

1. Click **"New +"** → **"Web Service"**
2. Connect your GitHub repo
3. Configure:
   - **Name**: `firstpatient-api`
   - **Region**: Oregon (or closest to your users)
   - **Branch**: `main`
   - **Runtime**: Docker
   - **Plan**: Starter ($7/mo) - **important: avoids cold starts**

### 3. Set Environment Variables

In Render dashboard, add these environment variables:

| Key | Value |
|-----|-------|
| `SUPABASE_URL` | `https://your-project.supabase.co` |
| `SUPABASE_SERVICE_KEY` | Your service role key (from Supabase dashboard) |
| `OPENAI_API_KEY` | Your OpenAI API key |
| `FRONTEND_URL` | `https://your-app.vercel.app` (set after Vercel deploy) |

### 4. Deploy

Click **"Create Web Service"** - Render will:
- Detect the Dockerfile
- Build the image
- Deploy automatically

You'll get a URL like: `https://firstpatient-api.onrender.com`

---

## Frontend Deployment (Vercel)

### 1. Deploy to Vercel

```bash
cd web
npm run build
npx vercel --prod
```

Or connect GitHub repo in Vercel dashboard.

### 2. Set Environment Variables

In Vercel project settings → Environment Variables:

| Key | Value |
|-----|-------|
| `VITE_API_URL` | `https://firstpatient-api.onrender.com` |
| `VITE_SUPABASE_URL` | `https://your-project.supabase.co` |
| `VITE_SUPABASE_ANON_KEY` | Your anon/public key |

### 3. Redeploy

Vercel will auto-redeploy when you update env vars, or trigger manually.

---

## Post-Deployment

### Update Backend CORS

After getting your Vercel URL, update `FRONTEND_URL` in Render:
1. Go to Render dashboard → your service → Environment
2. Set `FRONTEND_URL` to your Vercel URL
3. Render will auto-redeploy

### Verify Deployment

```bash
# Test backend health
curl https://firstpatient-api.onrender.com/health

# Should return: {"status":"healthy","version":"0.1.0"}
```

---

## Local Testing with Docker

```bash
# Build locally
docker build -t firstpatient-api .

# Run locally
docker run -p 8080:8080 \
    -e SUPABASE_URL="your-url" \
    -e SUPABASE_SERVICE_KEY="your-key" \
    -e OPENAI_API_KEY="your-key" \
    firstpatient-api

# Test
curl http://localhost:8080/health
```

---

## Cost Estimate

| Component | Plan | Cost |
|-----------|------|------|
| Render (Backend) | Starter | $7/mo |
| Vercel (Frontend) | Hobby | Free |
| Supabase (Database) | Free tier | $0/mo |
| OpenAI API | Pay-per-use | ~$5-20/mo |
| **Total** | | **~$12-27/mo** |

---

## Monitoring

### Render Logs
- Dashboard → Your service → Logs tab
- Or use Render CLI: `render logs firstpatient-api`

### Vercel Logs
- Dashboard → Your project → Deployments → Functions tab

---

## Troubleshooting

### CORS Errors
Make sure `FRONTEND_URL` in Render matches your exact Vercel URL (including `https://`).

### 502 Bad Gateway
Check Render logs - usually means the app crashed. Common causes:
- Missing environment variables
- Invalid API keys

### Slow First Request
If using free tier, there's a 30-50s cold start. Upgrade to Starter ($7/mo) to fix.

### Build Failures
Check that `Dockerfile` and `requirements.txt` are in the repo root.
