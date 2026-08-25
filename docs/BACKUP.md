# Backups

Firefly III (official image + MariaDB volume + upload volume) is the ledger. Estate does **not** store transactions. There is no second ledger to dump.

## What to run

```bash
python3 scripts/backup.py
```

Writes `~/EstateVault-backups/<UTC-timestamp>/` with:

- `firefly_iii_db.tar.gz` — MariaDB data
- `firefly_iii_upload.tar.gz` — Firefly upload volume
- `.env` — copied with mode `600` so restore has `FIREFLY_TOKEN` and DB passwords. **Never commit this file.**
- `estate.sqlite` — Estate metadata (contacts, documents) when US-040 has created it. Not a transaction ledger.
- `MANIFEST.txt`

Put backups on another disk (Time Machine, USB, NAS). A folder on this Mac does not survive a dead disk. Override the destination:

```bash
ESTATE_BACKUP_DIR=/Volumes/Offsite/estate python3 scripts/backup.py
```

Family sessions (US-050) must never receive `FIREFLY_TOKEN`. The dashboard HTML does not embed it. The copy in the backup folder is for the owner’s restore only.

## Restore (stable stack)

1. Stop stable: `docker compose down` (does not delete named volumes unless you pass `-v`; do not pass `-v` until you intend to replace them).
2. Restore each archive into the named volume (`estatevault_` prefix is the Compose project):

```bash
BACKUP=~/EstateVault-backups/20260824T120000Z
docker run --rm \
  -v estatevault_firefly_iii_db:/volume \
  -v "$BACKUP:/backup" \
  alpine:3.20 \
  sh -c 'rm -rf /volume/* /volume/..?* ; tar xzf /backup/firefly_iii_db.tar.gz -C /volume'
docker run --rm \
  -v estatevault_firefly_iii_upload:/volume \
  -v "$BACKUP:/backup" \
  alpine:3.20 \
  sh -c 'rm -rf /volume/* /volume/..?* ; tar xzf /backup/firefly_iii_upload.tar.gz -C /volume'
```

3. Copy `.env` back to the repo if needed (`chmod 600 .env`). Do not `git add .env`.
4. `./scripts/stable_up.sh`

If `estate.sqlite` is in the backup folder, copy it back to `data/estate.sqlite` in the repo (`chmod 600`). That file is contacts and instructions, not Firefly transactions.
