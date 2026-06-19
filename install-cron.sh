#!/bin/sh
set -e

ENV_FILE="/app/.env"
PYTHON_BIN="/usr/local/bin/python"

# ---- Check required vars ----
if [ -z "$PROVIDER_DOMAIN" ]; then
  echo "ERROR: PROVIDER_DOMAIN no está definida"
  exit 1
fi

if [ -z "$BACKUPS_FOLDER_ID" ]; then
  echo "ERROR: BACKUPS_FOLDER_ID no está definida"
  exit 1
fi

# ---- Auth: either EMAIL+PASSWORD or VALIDATION_KEY (session injection) ----
if [ -z "$VALIDATION_KEY" ] && { [ -z "$EMAIL" ] || [ -z "$PASSWORD" ]; }; then
  echo "ERROR: define EMAIL y PASSWORD, o bien VALIDATION_KEY (y SESSION_COOKIE)"
  exit 1
fi

# ---- Sync schedule: SYNC_CRON (fallback to legacy BACKUP_CRON) ----
SYNC_CRON="${SYNC_CRON:-$BACKUP_CRON}"
if [ -z "$SYNC_CRON" ]; then
  echo "ERROR: SYNC_CRON no está definida"
  exit 1
fi

# Direction: download (cloud -> local) | upload (local -> cloud) | both
SYNC_DIRECTION="${SYNC_DIRECTION:-download}"

# ---- Create .env file (cron cannot automatically reach env vars) ----
{
  echo "PROVIDER_DOMAIN=$PROVIDER_DOMAIN"
  echo "BACKUPS_FOLDER_ID=$BACKUPS_FOLDER_ID"
  echo "SYNC_DIRECTION=$SYNC_DIRECTION"
  [ -n "$EMAIL" ] && echo "EMAIL=$EMAIL"
  [ -n "$PASSWORD" ] && echo "PASSWORD=$PASSWORD"
  [ -n "$VALIDATION_KEY" ] && echo "VALIDATION_KEY=$VALIDATION_KEY"
  [ -n "$SESSION_COOKIE" ] && echo "SESSION_COOKIE=$SESSION_COOKIE"
  [ -n "$UNCATEGORIZED_FOLDER_ID" ] && echo "UNCATEGORIZED_FOLDER_ID=$UNCATEGORIZED_FOLDER_ID"
} > "$ENV_FILE"

chmod 600 "$ENV_FILE" || true

# ---- Create crontab ----
: > /tmp/crontab
echo "$SYNC_CRON $PYTHON_BIN /app/sync.py" >> /tmp/crontab

# Optional uncategorized job (only if both its vars are set)
if [ -n "$UNCATEGORIZED_CRON" ] && [ -n "$UNCATEGORIZED_FOLDER_ID" ]; then
  echo "$UNCATEGORIZED_CRON $PYTHON_BIN /app/uncategorized.py" >> /tmp/crontab
fi

crontab /tmp/crontab

# ---- Arrancar cron en primer plano ----
cron -f
