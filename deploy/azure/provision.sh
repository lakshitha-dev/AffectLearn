#!/usr/bin/env bash
# Provision AffectLearn on Azure: App Service (backend container) + Static Web Apps
# (frontend) + managed PostgreSQL + Redis + Blob (models) + ACR. CPU-only (no GPU).
#
# PREREQS: `az login` done, a subscription selected (`az account set -s <id>`),
#          Docker installed (to build/push the backend image).
# RUN:     edit the variables below, then `bash deploy/azure/provision.sh`.
# Idempotent-ish: re-running mostly no-ops or updates. Review cost before running.
set -euo pipefail

# ── EDIT THESE ─────────────────────────────────────────────────────────────────
RG="affectlearn-rg"
LOCATION="southeastasia"           # pick a region near you / with quota
ACR="affectlearnacr$RANDOM"        # must be globally unique, lowercase alphanumeric
APP_PLAN="affectlearn-plan"
BACKEND_APP="affectlearn-api-$RANDOM"   # -> https://<BACKEND_APP>.azurewebsites.net
SWA="affectlearn-web"
PG="affectlearn-pg-$RANDOM"        # globally unique
PG_ADMIN="aladmin"
PG_PASSWORD="$(openssl rand -base64 24)"   # save this!
REDIS="affectlearn-redis-$RANDOM"  # globally unique
STORAGE="affectlearnsa$RANDOM"     # globally unique, <=24 lowercase alnum
JWT_SECRET="$(openssl rand -hex 32)"
# ────────────────────────────────────────────────────────────────────────────────

say(){ echo -e "\n=== $* ==="; }

say "Resource group"; az group create -n "$RG" -l "$LOCATION" -o none

say "Container registry (ACR)"; az acr create -n "$ACR" -g "$RG" --sku Basic --admin-enabled true -o none

say "PostgreSQL Flexible (Burstable B1ms)"
az postgres flexible-server create -g "$RG" -n "$PG" -l "$LOCATION" \
  --admin-user "$PG_ADMIN" --admin-password "$PG_PASSWORD" \
  --sku-name Standard_B1ms --tier Burstable --version 16 \
  --storage-size 32 --public-access 0.0.0.0 -o none
az postgres flexible-server db create -g "$RG" -s "$PG" -d affectlearn -o none

say "Redis (Basic C0)"
az redis create -g "$RG" -n "$REDIS" -l "$LOCATION" --sku Basic --vm-size c0 -o none

say "Storage + models container"
az storage account create -g "$RG" -n "$STORAGE" -l "$LOCATION" --sku Standard_LRS -o none
STORAGE_KEY=$(az storage account keys list -g "$RG" -n "$STORAGE" --query "[0].value" -o tsv)
az storage container create --account-name "$STORAGE" --account-key "$STORAGE_KEY" -n models -o none
echo ">> Upload models next:  az storage blob upload-batch --account-name $STORAGE --account-key <key> -d models -s ../../backend/models"

say "Build + push backend image to ACR"
az acr build -r "$ACR" -t affectlearn-api:latest -f ../../backend/Dockerfile.prod ../../backend

say "App Service plan (Linux B2)"
az appservice plan create -g "$RG" -n "$APP_PLAN" --is-linux --sku B2 -o none

say "Backend Web App (container) + web sockets"
az webapp create -g "$RG" -p "$APP_PLAN" -n "$BACKEND_APP" \
  --deployment-container-image-name "$ACR.azurecr.io/affectlearn-api:latest" -o none
az webapp config set -g "$RG" -n "$BACKEND_APP" --web-sockets-enabled true -o none
ACR_PW=$(az acr credential show -n "$ACR" --query "passwords[0].value" -o tsv)
az webapp config container set -g "$RG" -n "$BACKEND_APP" \
  --container-image-name "$ACR.azurecr.io/affectlearn-api:latest" \
  --container-registry-url "https://$ACR.azurecr.io" \
  --container-registry-user "$ACR" --container-registry-password "$ACR_PW" -o none

REDIS_KEY=$(az redis list-keys -g "$RG" -n "$REDIS" --query primaryKey -o tsv)
SWA_HOST="https://$SWA.azurestaticapps.net"   # final host confirmed after SWA create
say "Backend app settings"
az webapp config appsettings set -g "$RG" -n "$BACKEND_APP" --settings \
  DATABASE_URL="postgresql+asyncpg://$PG_ADMIN:$PG_PASSWORD@$PG.postgres.database.azure.com:5432/affectlearn?ssl=require" \
  REDIS_URL="rediss://:$REDIS_KEY@$REDIS.redis.cache.windows.net:6380/0" \
  JWT_SECRET="$JWT_SECRET" ENVIRONMENT=production SEED_ON_STARTUP=false \
  EXPOSE_DEV_CREDENTIALS=false WEB_CONCURRENCY=2 \
  AFFECT_MODEL_PATH=models/cnn_lstm_best.onnx AFFECT_MODEL_KIND=engagement \
  BEHAVIORAL_MODEL_PATH=models/behavioral_bilstm.onnx \
  BEHAVIORAL_STATS_PATH=models/behavioral_feature_stats.json \
  AFFECT_DETECTION_MODE=auto CORS_ORIGINS="$SWA_HOST" \
  FACIAL_MODEL_URL="<set-a-blob-SAS-URL-to-cnn_lstm_best.onnx>" -o none

say "Static Web App (frontend)"
echo ">> Create the SWA linked to your GitHub repo (frontend app, Next.js):"
echo "   az staticwebapp create -g $RG -n $SWA -l $LOCATION \\"
echo "     --source https://github.com/<you>/AffectLearn --branch develop \\"
echo "     --app-location frontend --output-location .next --login-with-github"
echo "   Then set frontend env (SWA → Configuration):"
echo "     NEXT_PUBLIC_API_URL=https://$BACKEND_APP.azurewebsites.net/api/v1"
echo "     NEXT_PUBLIC_WS_URL=wss://$BACKEND_APP.azurewebsites.net"

cat <<EOF

=== DONE (core resources). SAVE THESE ===
  Backend:   https://$BACKEND_APP.azurewebsites.net
  PG admin:  $PG_ADMIN   PG password: $PG_PASSWORD
  JWT_SECRET: $JWT_SECRET
  Storage:   $STORAGE  (upload backend/models/* to the 'models' container)
Next: upload models, create the SWA, then verify /api/v1 health. See DEPLOY.md.
EOF
