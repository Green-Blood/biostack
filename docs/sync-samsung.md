# Automatic sync: Samsung phone + Galaxy Watch

The watch's steps, sleep, heart rate, HRV, skin temperature, weight and body fat reach BioStack on their own,
with no export by hand.

```
Galaxy Watch -> Samsung Health -> Health Connect -> Health Connect Webhook app -> POST /api/v1/health-sync
```

The server needs nothing extra: the webhook stores each batch as it arrives. `ENABLE_SCHEDULER` is not involved.

## 1. Samsung Health writes to Health Connect

Samsung Health → Settings → Health Connect (on some One UI versions: "Data sharing and privacy"). Allow it to
write steps, sleep, heart rate, HRV, skin temperature, blood oxygen, weight and body fat. Not every Samsung
version shares every type; after the first sync, check which values actually appear.

## 2. The phone reaches the server

Install Tailscale on the phone and sign in to the same tailnet as the server. Check it in the phone's browser:
`https://<server-tailscale-name>:8443` should open BioStack (see `docs/SERVER.md`, "Publish to your devices").
The web app forwards `/api/health-sync` and the `X-API-Key` header to the API.

## 3. Health Connect Webhook

Install [Health Connect Webhook](https://github.com/mcnaveen/health-connect-webhook)
(Google Play `com.hcwebhook.app`, or the beta APKs from its GitHub releases) and give it read access to the same
types as step 1.

- **Webhook URL:** `https://<server-tailscale-name>:8443/api/health-sync`
- **Custom header:** `X-API-Key` = `API_SECRET_KEY` from the server's `.env`
- **Payload timestamps:** Local time (Settings → App settings; the default on new installs). With UTC, readings
  near midnight are filed under the wrong day.
- **Schedule:** Interval 60 min, or fixed times such as 08:00 and 21:00. Press **Sync Now** once to test.

## How the server reads it

`services/health_payload.py` (`_collect_hc_webhook`) turns the app's JSON into daily values:

| App field | BioStack value | Per day |
|---|---|---|
| `steps[].count` | steps | sum |
| `sleep[]` stages (awake stages left out) | sleep total / deep / REM | sum, on the day you wake up |
| `resting_heart_rate[].bpm` | resting HR | mean |
| `heart_rate_variability[].rmssd_millis` | HRV (RMSSD, stored in `hrv_sdnn`) | mean |
| `skin_temperature[].delta_celsius` | skin temperature deviation | mean |
| `weight[].kilograms`, `body_fat[].percentage` | body measurements | latest |

The app sends only records that are new since its last sync, so steps and sleep add onto the totals an earlier
sync stored (`routers/health_sync.py`, `_add_to_synced_totals`). A day that came from the Samsung ZIP import is
replaced by the first sync, not added to.

## Backfill

The one-time ZIP import (Settings → Samsung Health) is still the way to load history. The webhook covers the
last 48 hours on its first run and new records after that.
