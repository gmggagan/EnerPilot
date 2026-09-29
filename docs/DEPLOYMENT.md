# Deploying EnerPilot online (free)

Two free setups work. Both keep the app public and give you a link that works on any device.

| | **A. Vercel (frontend) + Render (backend)** | **B. Hugging Face Spaces (all-in-one)** |
|---|---|---|
| Cost / card | Free, no card | Free, no card |
| Backend resources | 512 MB RAM, very small CPU share | 16 GB RAM, 2 vCPU |
| EnerPilot needs | ~220 MB RAM (measured) ✓ | ✓ |
| Sleeps when idle | After 15 min, wake takes ~1–3 min | After ~48 h |
| Deploys from GitHub | Yes, automatic on every push | Upload or git push |

Both work. **B is faster and sleeps far less.** **A fits a VS Code → GitHub workflow.**

---

## A. GitHub → Vercel (frontend) + Render (backend)

### 1. Push the project to GitHub
Create a new GitHub repository whose **root** is this `enerpilot` folder, so `render.yaml`, `backend/` and `frontend/` sit at the top level.

In VS Code: *Source Control → Publish to GitHub*, or:
```bash
git init
git add .
git commit -m "EnerPilot"
git branch -M main
git remote add origin https://github.com/<you>/enerpilot.git
git push -u origin main
```
`.gitignore` already keeps `node_modules`, `dist`, caches and `.venv` out of the repo.

### 2. Backend on Render
1. Go to https://render.com and sign in with GitHub.
2. **New → Blueprint** → select the repo. Render reads `render.yaml`:
   - root `backend`, Python 3.11.9;
   - build `pip install -r requirements.txt`;
   - start `uvicorn main:app --host 0.0.0.0 --port $PORT`;
   - health check `/api/v1/ping`;
   - `ENERPILOT_WARM_CACHE=0`.
3. **Apply.** The first build takes about 5 minutes.
4. Copy the service URL, e.g. `https://enerpilot-api.onrender.com`.
5. Check it by opening `https://enerpilot-api.onrender.com/api/v1/health`.
   - The first call can take 1–3 minutes while the model trains on the small free CPU.
   - After that, calls are quick.

> Manual alternative to the Blueprint: **New → Web Service** with root directory `backend` and the same build/start commands. Add the env vars `PYTHON_VERSION=3.11.9` and `ENERPILOT_WARM_CACHE=0`, and set the health check path to `/api/v1/ping`.

### 3. Frontend on Vercel
1. Go to https://vercel.com and sign in with GitHub → **Add New → Project** → select the repo.
2. **Root Directory:** `frontend`. The framework is detected as **Vite**; build `npm run build`, output `dist`.
3. **Environment Variables:** `VITE_API_BASE` = your Render URL, e.g. `https://enerpilot-api.onrender.com`.
4. **Deploy.** The app is at `https://<project>.vercel.app`.
5. If you change `VITE_API_BASE` later, **redeploy**: the value is baked in at build time.

### 4. Before a demo (Render free sleeps after 15 min)
- **Wake it early:** open the Vercel link **3–5 minutes before** the demo. The page shows "Starting ENERPILOT…" and retries automatically until the backend is up.
- **Or keep it awake:** a free monitor (e.g. UptimeRobot) can call `https://<render-url>/api/v1/ping` every 5 minutes. One always-on service stays within Render's free monthly hours.

---

## B. Hugging Face Spaces (single container)
The root `Dockerfile`:
- builds the UI;
- serves UI + API on port **7860** as a non-root user;
- keeps its data in `/tmp/enerpilot`.

The YAML header at the top of `README.md` configures the Space.

1. Sign up at https://huggingface.co.
2. **New → Space**:
   - SDK **Docker → Blank**
   - Hardware **CPU basic · free**
   - Visibility Public
3. **Files → Add file → Upload files:** drag in the *contents* of the clean `enerpilot_deploy` folder, so `Dockerfile` and `README.md` sit at the top level. **Commit.**
4. Wait for the build (5–10 min) and the first start (~1 min).
5. Your link is `https://<username>-<space>.hf.space`.

To use git instead:
- run `git lfs install` first;
- Hugging Face requires binary files in LFS: run `git lfs track "*.png"` before `git add`;
- log in with an access token, not your password.

---

## Troubleshooting
| Symptom | Fix |
|---|---|
| Vercel page says "Backend unavailable" | Check `VITE_API_BASE` (no typo, `https://`), then redeploy Vercel. Open `<render-url>/api/v1/ping` to see if the backend is awake. |
| Stuck on "Starting ENERPILOT…" for minutes | Normal after Render slept. It retries automatically. Check Render **Logs** for errors. |
| Render build fails on Python packages | Make sure `PYTHON_VERSION=3.11.9` is set. |
| Weather source shows "synthetic-fallback" | The host couldn't reach Open-Meteo/PVGIS at that moment. The app still works on demo data and retries on the next hourly rebuild. |
