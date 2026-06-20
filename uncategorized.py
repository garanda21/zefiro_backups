import os
import sys
import fcntl
from dotenv import load_dotenv
from cloud_manager import CloudManager, SessionExpiredError

load_dotenv("/app/.env")

PROVIDER_DOMAIN = os.environ["PROVIDER_DOMAIN"]
EMAIL = os.environ.get("EMAIL")
PASSWORD = os.environ.get("PASSWORD")
UNCATEGORIZED_FOLDER_ID = os.environ["UNCATEGORIZED_FOLDER_ID"]
VALIDATION_KEY = os.environ.get("VALIDATION_KEY")
SESSION_COOKIE = os.environ.get("SESSION_COOKIE")

LOCK_PATH = "/tmp/zefiro_uncategorized.lock"

def run():
    cm = CloudManager(
        PROVIDER_DOMAIN,
        username=EMAIL,
        password=PASSWORD,
        validationkey=VALIDATION_KEY,
        session_cookie=SESSION_COOKIE,
    )
    if VALIDATION_KEY:
        cm.check_session()
    cm.move_uncategorized_timeline(UNCATEGORIZED_FOLDER_ID)

def main():
    lock_fh = open(LOCK_PATH, "w")
    try:
        fcntl.flock(lock_fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        print("Ya hay una ejecución de uncategorized en curso; se omite.")
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
