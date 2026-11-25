# Running BioStack on a home server

BioStack runs as three Docker containers (`api`, `web`, `bot`) from `docker-compose.yml`. Everything it stores is in `./state/` next to the compose file: `biostack.db`, `data/` (files, imports) and `backups/`. Nothing is published to the internet: the web port is bound to `127.0.0.1` and `tailscale serve` shows it to your own devices only.

## One-time setup

1. **Docker** with the Compose plugin, and your user in the `docker` group.
2. **Clone** the repository on the server. For a private repository, create a read-only deploy key on the server and add it to the repository (Settings, Deploy keys), then clone through an SSH host alias that uses that key.
3. **`.env`** in the repository folder (copy `.env.example`):
   - `API_SECRET_KEY`: a long random value (`openssl rand -hex 32`). The stack refuses to start without it.
   - `ALLOWED_HOSTS`: the hostname you open BioStack under, for example `myserver.tail1234.ts.net`. Without it the web app only answers on `localhost`.
   - `GEMINI_API_KEY`, `GEMINI_MODEL`: for Ask the AI, PDF reading and the daily summary.
   - `ENABLE_SCHEDULER=1`: refresh weather and air quality every 3 hours once a location is set in Settings.
4. **Start**: `bash scripts/server_deploy.sh`. The first run builds the images (a few minutes).
5. **Publish to your devices**: `sudo tailscale serve --bg --https=8443 http://127.0.0.1:3410`, then open `https://<your-tailscale-name>:8443` on any device signed in to your tailnet. (443 may already be taken by something else; 8443 and 10000 are the other ports `tailscale serve` accepts.)
6. **Nightly backup** (as your own user, no sudo): `crontab -e` and add

   ```
   0 3 * * * cd $HOME/biostack && docker compose exec -T api python -m scripts.backup >> state/backup.log 2>&1
   ```

## Updating

From your laptop, with everything committed:

```bash
./scripts/deploy.sh
```

It pushes the current branch, then on the server: pulls it, writes a backup (keeping the 30 newest), rebuilds, waits for the API and web app to be healthy, and rolls the code back to the previous commit if they are not. Database migrations run when the API starts.

After an update that adds organ history for the first time, tag the existing scans once (safe to re-run): `docker compose exec api python -m scripts.backfill_scans`. Run it after the deploy, because the deploy is what creates the new tables; it stops with a message if they are missing. Your data is in `state/`, outside the images, so an update never replaces it.

## Backups and restore

Each backup is `state/backups/biostack-YYYYmmdd-HHMMSS.tar.gz`: a consistent copy of the database (made with SQLite's backup API, safe while the app is running) and the whole `data/` folder. The nightly job keeps 14; the pre-update backups share the same folder.

Restore: `bash scripts/restore.sh state/backups/<archive>`. It stops the app, moves the current database and files to `state/before-restore-<time>/`, unpacks the archive and starts the app again.

These backups live on the same disk as the data. They protect against mistakes and bad updates, not against losing the machine: copy `state/backups/` somewhere else now and then.

## Telegram bot

1. In Telegram, talk to **@BotFather**, send `/newbot`, and copy the token into `TELEGRAM_BOT_TOKEN` in the server's `.env`.
2. Restart the bot: `docker compose up -d bot`. Send `/id` to your new bot; it answers with your number.
3. Put that number in `TELEGRAM_OWNER_ID`, then `docker compose up -d bot` again.

The bot answers only that one account, in a private chat; everyone else is ignored. It long-polls Telegram, so it needs no open port.

| You send | It does |
| --- | --- |
| Text | Asks the AI with your whole record, like the Ask the AI page |
| A photo | Same, with the photo; the caption is the question |
| A voice note | Transcribes it (Gemini), shows what it heard, then answers |
| `/today` | Today's summary |
| `/export` | Sends the one-click ZIP of everything (up to 50 MB) |
| `/id` | Shows your Telegram id (works for anyone) |

`BOT_LANG` (`ru` or `en`) sets the language of the bot's own messages and of the answers.

## Phone health sync

The web app forwards the `X-API-Key` header, so an automation on your phone (for example iOS Health Auto Export) can post to `https://<your-tailscale-name>:8443/api/health-sync` with `X-API-Key` set to the server's `API_SECRET_KEY`. The phone must be signed in to Tailscale.

## Samsung Health import

Easiest: open BioStack through Tailscale, go to Settings and use the Samsung Health card. The upload streams through the web proxy to the API, which reads it and deletes it afterwards.

From the command line, copy the ZIP into the API container and run the importer (the container runs as `BIOSTACK_UID`, not root, and the importer keeps the ZIP it is given):

```bash
chmod a+r ~/export.zip                                  # docker cp may keep the file root-owned, and exports are often 0600
docker compose cp ~/export.zip api:/tmp/sh.zip
docker compose exec api python -m scripts.import_samsung_health /tmp/sh.zip   # prints the summary as JSON
docker compose exec -u root api rm /tmp/sh.zip          # the CLI does not delete it; /tmp is sticky, so root removes it
```

It uses the server's own database (`/state/biostack.db`) and needs the migrations applied, which the API container does on every start.

## Useful commands (on the server, in the repository folder)

```bash
docker compose ps                    # what is running and healthy
docker compose logs -f api           # follow the API log (also: web, bot)
docker compose restart web           # restart one service
docker compose exec api python -m scripts.backfill_scans   # tag and read existing scans (after deploy)
bash scripts/server_deploy.sh        # update to the latest commit of the checked-out branch
```
