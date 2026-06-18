import os
from dotenv import load_dotenv
from cloud_manager import CloudManager
load_dotenv("/app/.env")

PROVIDER_DOMAIN = os.environ["PROVIDER_DOMAIN"]
EMAIL = os.environ.get("EMAIL")
PASSWORD = os.environ.get("PASSWORD")
BACKUPS_FOLDER_ID = os.environ["BACKUPS_FOLDER_ID"]
VALIDATION_KEY = os.environ.get("VALIDATION_KEY")
SESSION_COOKIE = os.environ.get("SESSION_COOKIE")

def main():
    cm = CloudManager(
        PROVIDER_DOMAIN,
        username=EMAIL,
        password=PASSWORD,
        validationkey=VALIDATION_KEY,
        session_cookie=SESSION_COOKIE,
    )
    cm.sync_remote_path("/backups", BACKUPS_FOLDER_ID)

if __name__ == "__main__":
    main()
