# Zefiro Backups

![image](logo.png)

[Zefiro](https://zefiro.me) is a cloud storage provider that, in addition to offering plans to end users, also provides its service to some internet service providers such as Movistar or O2, allowing them to offer it free of charge to their customers when they subscribe to an internet plan.

The main goal of Zefiro Backups is to help you create local backups of the files you have stored in this cloud storage service. However, Zefiro’s user interface makes file organization somewhat complex, so this container also helps you with that task.

Although Zefiro provides folders and albums to organize your photos, videos, and other files, organizing photos and videos can sometimes be difficult because when they are uploaded from the mobile app, everything appears together in a single timeline. This makes it hard to know which items have already been organized into a folder or album.

To solve this, Zefiro Backups proposes creating two folders that the container will work with:

UNCATEGORIZED_FOLDER: Zefiro Backups will automatically move all multimedia content uploaded from the mobile app into this folder, so you can then review it and move it to the folder you consider appropriate.

BACKUPS_FOLDER: This folder will contain the rest of the folders where you will organize all your already reviewed content. It will be treated as the root directory from which local backups are created.

It’s up to you to create UNCATEGORIZED_FOLDER inside BACKUPS_FOLDEE to include “uncategorized” photos and videos in your backups.

## Envionrment vars

| Var      | Description |
| -------- | ------- |
| PROVIDER_DOMAIN  | Zefiro / Your ISP's domain    |
| EMAIL | your account email     |
| PASSWORD    | your account password    |
| VALIDATION_KEY | a validationkey captured from an authenticated browser session — see *Authentication* below |
| SESSION_COOKIE | the `JSESSIONID` cookie value from the **same** browser session (required together with VALIDATION_KEY) |
| BACKUPS_FOLDER_ID | ID of the root folder to sync (cloud side) / mirror (local side) |
| UNCATEGORIZED_FOLDER_ID | ID of the folder to automatically move all the content uploaded from apps |
| SYNC_DIRECTION | sync direction: `download` (cloud → local, default), `upload` (local → cloud) or `both` |
| SYNC_CRON | cronjob expression to schedule the sync (replaces `BACKUP_CRON`, which still works as a fallback) |
| UNCATEGORIZED_CRON | cronjob expression to automatically move app uploaded content to UNCATEGORIZED_FOLDER_ID |

## Authentication

> **Important:** some providers (e.g. O2 Spain at `cloud.o2online.es`) have placed the
> `/sapi/login` endpoint behind a CloudFront/WAF anti-bot layer and enabled multi-factor
> authentication (MFA). Automated user+password login from a script is blocked there
> (the server returns `403 Request blocked` or `401`). The data endpoints
> (listing, downloading, moving files, etc.) are **not** affected — they only need a
> valid `validationkey`.

To work around this, skip the automated login and inject a session captured from your
browser:

1. Log in to your provider's cloud storage in a desktop browser.
2. Open the browser's developer tools → **Network** tab.
3. Trigger any action and look for a request such as
   `/sapi/media/folder?action=get&validationkey=xxxxx`.
4. Copy the `validationkey` value from the request URL → set it as `VALIDATION_KEY`.
5. From the **Request Headers** of that same request, copy the `JSESSIONID` cookie value
   → set it as `SESSION_COOKIE`.

Both values are required together: the validationkey alone returns `401` — it only
authenticates when paired with the matching `JSESSIONID` session cookie. When both are
set, `EMAIL`/`PASSWORD` are not required. The session is tied to your browser login and
**will eventually expire**, so you'll need to refresh both values periodically. If your
provider does **not** enforce the WAF/MFA (e.g. plain Zefiro), you can keep using
`EMAIL`/`PASSWORD` and leave `VALIDATION_KEY`/`SESSION_COOKIE` empty.

Available provider domains:

| Service | Domain |
|---------|--------|
| Zefiro | zefiro.me |
| Movistar (Spain) | micloud.movistar.es |
| O2 (Spain) | cloud.o2online.es |

To get a folder ID, you must log in to your ISP or Zefiro storage service from a computer and open your browser’s developer tools.
Look for the request to /sapi/media/folder?action=get&validationkey=xxxxx.
Check the JSON object on the Preview Tab

## The volume

The volume maps the container path that is synced (/backups) to a path on your host disk.

## Sync direction

Set `SYNC_DIRECTION` to control how `/backups` is synchronized with the cloud:

- `download` (default): cloud → local. Downloads remote files that are not yet present locally.
- `upload`: local → cloud. Uploads local files/folders that are not yet present in the cloud.
- `both`: runs download first, then upload.

## About the sync process

The sync only checks whether a file already exists **by filename** (it does not yet compare
sizes, dates or hashes). This means:

- **download**: if a file is modified directly in the cloud, it will not be downloaded again
  as long as a file with the same name already exists locally.
- **upload**: a local file is uploaded only if no file with the same name exists in the target
  cloud folder. Updating already-existing files is planned for a future phase.

The upload is **non-destructive**: it never deletes anything from the cloud. It only creates
missing folders and uploads missing files.

### Robustness (large uploads)

The upload is built to survive big bulk transfers:

- **Single instance**: a lock (`/tmp/zefiro_sync.lock`) prevents overlapping runs, so a slow
  upload won't be run again in parallel by the next cron tick.
- **Retries**: each file is retried a few times with backoff on network errors; if a file
  still fails it is logged and the run continues with the rest. Because matching is by name,
  re-running resumes where it left off.
- **Size limit**: files larger than the provider limit (`sapi.upload.max-size-in-mb`, e.g.
  4096 MB on O2) are skipped with a log line instead of aborting the run.
- **Expired session**: detected up front and during upload, with a clear message to refresh
  `VALIDATION_KEY`/`SESSION_COOKIE`.
- A summary line is printed at the end (uploaded / already existed / skipped / failed).

### First (huge) upload tip

For a large initial backup, run it **once, manually**, instead of relying on a frequent cron:

```bash
docker compose exec zefiro_backups python /app/sync.py
```

Keep `SYNC_CRON` infrequent (e.g. hourly) for the incremental syncs afterwards. Running it
too frequently can race with the provider's **asynchronous indexing** (a just-uploaded file
may not show up in the listing yet), which could re-upload it as a `(1)` duplicate.

## Disclaimer

**This software is provided “as is”, without any express or implied warranty. The author assumes no responsibility or liability for any errors, bugs, or unexpected behavior in the code, nor for any damage, data loss, or other issues that may result from its use.

Use this software at your own risk.**

## Dockerhub

Find Zefiro Backups on [Dockerhub](https://hub.docker.com/r/molinaig/zefiro_backups)
