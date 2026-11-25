# Off-site backups — plan (not implemented yet)

Status: proposal, 2026-11-12. Nothing here is built yet.

## Why

The nightly job (`crontab`, 03:00) and every deploy write `state/backups/biostack-YYYYmmdd-HHMMSS.tar.gz` on the server: the database and the whole `data/` folder (~135 MB today). They live on the **same disk** as the data. They protect against mistakes and bad updates, not against losing the machine (disk failure, theft, a broken OS install). One copy has to live somewhere else.

## What a good setup looks like

- **Automatic.** Nobody remembers to copy files by hand.
- **Encrypted before it leaves the server** when it goes to a cloud. These are medical records; the cloud provider should only ever see ciphertext.
- **Versioned.** Several days or weeks of history, so a bad backup does not overwrite the only good one.
- **Restorable.** A copied archive feeds straight into `scripts/restore.sh`. Test a restore once after setting this up, then every few months.
- **Quiet on success, loud on failure.** A failed copy should show up somewhere (the Telegram bot is the natural place).

## Option A — pull to the laptop (simplest, free, private)

The Mac pulls new archives from the server over Tailscale/SSH.

- `rsync -a <your-server>:biostack/state/backups/ ~/BioStack-backups/` (only copies new archives).
- Run by a `launchd` job on the Mac, every few hours. It simply catches up after the laptop was asleep or away.
- Keep the newest ~30 locally (a small prune script or `find -mtime`).
- Optional: point the destination at an external disk or a Time Machine–covered folder to get a third copy.

Pros: no cloud, no extra accounts, data never leaves your devices, zero cost.
Cons: only copies while the laptop is on and in reach of the server; laptop and server are often in the same home (fire/theft hit both).

## Option B — encrypted copy to Google Drive (off-site)

The server pushes archives to Google Drive with `rclone`, encrypted.

- Install `rclone` on the server, create a `drive` remote (one-time browser sign-in; can be done from the laptop with `rclone authorize`), then a `crypt` remote on top of it with a long password kept in a password manager (lose it and the backups are unreadable).
- After the nightly backup: `rclone copy state/backups/ gdrive-crypt:biostack-backups/ --max-age 48h`.
- Retention: `rclone delete --min-age 60d` on the remote (or keep weekly ones longer).
- 135 MB per archive × daily = a few GB a month before pruning; Drive's free 15 GB is enough with a 30–60 day window.

Pros: survives losing the whole home, runs without the laptop.
Cons: a cloud account in the loop (ciphertext only), one more secret to keep (the crypt password), a Google sign-in token on the server.

## Recommendation

Do **both**, in this order:

1. **A first** (an evening's work): laptop pull via `launchd` + rsync. Immediate protection against the server's disk dying.
2. **B next**: rclone crypt to Google Drive, run right after the 03:00 backup, 60-day retention. Protection against losing the home.
3. Then: a weekly Telegram message "last off-site copy: <date>, <size>", and a restore drill into a scratch folder.

## To decide before building

- Laptop folder for the copies (default `~/BioStack-backups/`), and whether an external disk should get them too.
- Google account to use, and where the crypt password lives.
- Retention: how many days locally and in Drive.
