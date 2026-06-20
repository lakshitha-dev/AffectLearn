# Deploying AffectLearn to Azure (CPU-first pilot)

Target architecture (no GPU until Phase B):

```
Browser ── Static Web Apps (Next.js frontend)
              │  HTTPS / WSS
              ▼
        App Service (Linux container)  ── FastAPI + WebSocket
          ├─ behavioral ONNX  (in image, CPU)
          ├─ facial ONNX      (fetched from Blob, CPU)
          ├─ PostgreSQL  → Azure Database for PostgreSQL (Flexible)
          ├─ Redis       → Azure Cache for Redis
          └─ vLLM/LLM    → (Phase B only) NC-series GPU VM
        Blob Storage ── model artifacts (facial ONNX, LLM)
        ACR ── backend container image
```

**You run these steps** (your Azure account + credit). I generated the Dockerfile.prod,
entrypoint, SWA config, env template, and `provision.sh`.

---

## 0. Prerequisites
```bash
az login
az account set -s <your-subscription-id>
az extension add -n containerapp 2>/dev/null || true   # not needed for App Service path
# Docker Desktop running (for the image build, or use `az acr build` which builds in cloud)
```
Request a region with capacity (e.g. `southeastasia`). **No GPU quota needed for CPU-first.**

## 1. Provision core resources
Edit the variables at the top of `deploy/azure/provision.sh`, then:
```bash
cd deploy/azure
bash provision.sh        # creates RG, ACR, Postgres, Redis, Storage, backend Web App; builds+pushes image
```
**Save the printed PG password / JWT_SECRET / storage name.**

## 2. Upload the models to Blob
```bash
# behavioral (small) is baked into the image; upload the 46MB facial model:
az storage blob upload-batch --account-name <STORAGE> --account-key <KEY> \
  -d models -s ../../backend/models     # uploads cnn_lstm_best.onnx etc.
# Make a SAS URL for the facial model and set it so the container fetches it:
SAS=$(az storage blob generate-sas --account-name <STORAGE> --account-key <KEY> \
  -c models -n cnn_lstm_best.onnx --permissions r --expiry 2027-01-01 --https-only -o tsv --full-uri)
az webapp config appsettings set -g affectlearn-rg -n <BACKEND_APP> --settings FACIAL_MODEL_URL="$SAS"
```
(Tip: to skip the fetch entirely, copy `cnn_lstm_best.onnx` into `backend/models/` and remove
the gitignore line before `az acr build` so it's baked into the image — simpler, bigger image.)

## 3. Run DB migrations
The container entrypoint runs `alembic upgrade head` automatically on boot. Confirm in
**App Service → Log stream**. (Manual fallback: `az webapp ssh` then `alembic upgrade head`.)

## 4. Deploy the frontend (Static Web Apps)
```bash
az staticwebapp create -g affectlearn-rg -n affectlearn-web -l southeastasia \
  --source https://github.com/<you>/AffectLearn --branch develop \
  --app-location frontend --output-location .next --login-with-github
```
Then in **SWA → Configuration** set:
```
NEXT_PUBLIC_API_URL = https://<BACKEND_APP>.azurewebsites.net/api/v1
NEXT_PUBLIC_WS_URL  = wss://<BACKEND_APP>.azurewebsites.net
```
And set the backend's `CORS_ORIGINS` to the SWA URL (`https://affectlearn-web.azurestaticapps.net`).

> **If SSR fights you on SWA** (your app is SSR Next.js, not static): host the frontend on
> App Service instead — `az webapp create` a Node 20 app, set the same `NEXT_PUBLIC_*`, and
> deploy with `next build && next start`. Everything else is unchanged.

## 5. Verify
```bash
curl https://<BACKEND_APP>.azurewebsites.net/api/v1/health   # or /docs
```
Open the SWA URL, register a learner, confirm the lesson WebSocket connects and behavioral/
facial affect cycles run (App Service Log stream shows `engagement_model_loaded` +
`behavioral` inference). Fusion is active when both modalities are present.

## 6. (Phase B only) Add the GPU LLM
```bash
# Request NC-series quota first (Portal → Quotas). Then:
az vm create -g affectlearn-rg -n affectlearn-gpu --image Ubuntu2204 \
  --size Standard_NC4as_T4_v3 --admin-username azureuser --generate-ssh-keys
# SSH in, install NVIDIA driver + Docker + nvidia-container-toolkit, then run vLLM:
#   docker run --gpus all -p 8000:8000 vllm/vllm-openai:latest \
#     --model <merged-llama-3-8b> --served-model-name affectlearn/llama-3-8b-pedagogical
# Point the backend at it (use the VM's private IP; lock the NSG to the App Service subnet):
az webapp config appsettings set -g affectlearn-rg -n <BACKEND_APP> \
  --settings VLLM_ENDPOINT="http://<gpu-vm-ip>:8000"
```
**Cost control:** `az vm deallocate` the GPU VM when not in a session (T4 ≈ $0.5-1+/hr).
Phase A needs no GPU at all (log-only).

---

## Cost sketch (pilot, CPU-first)
| Resource | SKU | ~Monthly |
|---|---|---|
| App Service plan | B2 (2 vCPU/3.5GB) | ~$30-55 |
| PostgreSQL Flexible | B1ms | ~$15-25 |
| Redis | Basic C0 | ~$16 |
| Static Web Apps | Free/Standard | $0-9 |
| Storage + ACR | minimal | ~$2-5 |
| **GPU VM (Phase B only)** | NC4as_T4_v3 | ~$0.5-1+/hr (deallocate when idle) |

## Notes
- App Service **must** have web sockets enabled (provision.sh does this) — the affect loop is WS.
- Azure Postgres requires **SSL** (`?ssl=require`) and Redis uses **TLS** (`rediss://:KEY@...:6380`).
- Keep `SEED_ON_STARTUP=false` / `EXPOSE_DEV_CREDENTIALS=false` in production.
- Don't commit the 46MB facial ONNX (gitignored) — it's served from Blob or baked at build.
