import os
import sys
import fcntl
from dotenv import load_dotenv
from cloud_manager import CloudManager, SessionExpiredError
load_dotenv("/app/.env")

PROVIDER_DOMAIN = os.environ["PROVIDER_DOMAIN"]
EMAIL = os.environ.get("EMAIL")
PASSWORD = os.environ.get("PASSWORD")
BACKUPS_FOLDER_ID = os.environ["BACKUPS_FOLDER_ID"]
VALIDATION_KEY = os.environ.get("VALIDATION_KEY")
SESSION_COOKIE = os.environ.get("SESSION_COOKIE")
# download (cloud -> local) | upload (local -> cloud) | both
SYNC_DIRECTION = os.environ.get("SYNC_DIRECTION", "download").lower()

LOCK_PATH = "/tmp/zefiro_sync.lock"

def run():
    if SYNC_DIRECTION not in ("download", "upload", "both"):
        raise SystemExit(
            f"SYNC_DIRECTION invalido: '{SYNC_DIRECTION}'. Usa download, upload o both."
        )
    cm = CloudManager(
        PROVIDER_DOMAIN,
        username=EMAIL,
        password=PASSWORD,
        validationkey=VALIDATION_KEY,
        session_cookie=SESSION_COOKIE,
    )
    # Fail fast with a clear message if the injected session has expired.
    if VALIDATION_KEY:
        cm.check_session()
    if SYNC_DIRECTION in ("download", "both"):
        print("== Sincronizando cloud -> local ==")
        cm.sync_remote_path("/backups", BACKUPS_FOLDER_ID)
    if SYNC_DIRECTION in ("upload", "both"):
        print("== Sincronizando local -> cloud ==")
        cm.upload_local_path("/backups", BACKUPS_FOLDER_ID)

def main():
    # Single-instance lock: prevents overlapping runs (e.g. a long bulk upload
    # while cron fires the next one), which would cause duplicates and races.
    lock_fh = open(LOCK_PATH, "w")
    try:
        fcntl.flock(lock_fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        print("Ya hay una sincronización en curso; se omite esta ejecución.")
        return
    try:
        run()
    except SessionExpiredError as e:
        print("ERROR: %s" % e)
        sys.exit(1)
    finally:
        fcntl.flock(lock_fh, fcntl.LOCK_UN)
        lock_fh.close()

if __name__ == "__main__":
    main()
