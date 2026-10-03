# Changelog

Operational changes to the `rf-pi` Docker stack, newest first
(`.cursor/rules/030-Deployment-Procedure.mdc` step 6). Dates are local (PDT).

## 2026-10-03 — Phase 4 hardening (review §2 BME680, §5 rfpi)

Source: `/home/pi/REVIEW-2026-10-03.md`. File edits only; applied with the
commands under *Apply* below.

### bme680-mqtt/bme680_mqtt.py
- `connect_async()` + `loop_start()` with keepalive 30 s: a broker that is down
  at boot is retried instead of crash-looping the container.
- `enable_logger()` routed to stdout at INFO in the existing `log()` style;
  `reconnect_delay_set(1, 15)`; `on_disconnect` logs the reason and whether
  the broker or the network dropped the session.
- `publish_state()` checks `client.is_connected()` and the publish return code;
  the healthcheck heartbeat is touched only on success. After 10 consecutive
  failed cycles the process exits 1 so `restart: unless-stopped` recovers it.
- Subscribes to `homeassistant/status`; on the `online` birth message it
  republishes availability + discovery (`announce()`), as it does on every
  connect.
- Discovery payloads gain `expire_after = INTERVAL*3 + 15`; availability
  `online` (retained) is re-asserted every publish cycle.
- Unchanged: LWT, clean-shutdown `offline`, topic layout, heartbeat file.

### docker-compose.yml
- Removed the `healthcheck.test` overrides on all nine upstream images
  (ultrafeeder, piaware, fr24, pfclient, rbfeeder, planewatch, adsbhub,
  opensky, adsbexchange); each ships a real HEALTHCHECK (verified with
  `docker image inspect`). ultrafeeder keeps a cadence-only override
  (60 s / 30 s / 3 / start 120 s) because feeders gate on `service_healthy`
  and upstream's 600 s interval would delay them 10 min on a cold start.
- `pids_limit: 256` on ultrafeeder (86 tasks live), `128` on each feeder
  (max 29 live). No memory limits yet (memory cgroup disabled until reboot).
- ultrafeeder: `/dev:/dev` -> `/dev/bus/usb:/dev/bus/usb` (readsb's only
  device fd is `/dev/bus/usb/001/002`; `c 189:* rwm` rule already present).
- Removed the dead `rtl-airband` service (superseded by pluto-airband's
  `airband-feeds.service` on the host) and the redundant `logging:` blocks on
  bme680/promtail (daemon default is `local`, 50m x 3).
- promtail: positions on the new named volume `promtail-positions`
  (`/var/lib/promtail`); dropped the unused `/var/lib/docker/containers`
  mount; docker socket mounted `:ro`.

### promtail-config.yml
- `positions.filename: /var/lib/promtail/positions.yaml`.
- Removed `tls_config.insecure_skip_verify: true`: the Loki endpoint presents
  a publicly trusted Let's Encrypt certificate (`curl` without `-k` -> 401 =
  TLS OK / auth required; `openssl s_client` verify return code 0).

### Secrets / repo hygiene
- `.env` backed up to `.env.bak-2026-10-03` (mode 600, gitignored), then
  trimmed to the 32 variables the stack references and `chmod 600`. Removed:
  `EMAIL`, `FEEDER_ALT_FT`, `RADARBOX_SHARING_KEY`, `RV_FEEDER_KEY`,
  `METERMON_USER`, `METERMON_PASS`, `MQTT_HOST_IP`, `WUD_USER`, `WUD_HASH`,
  `GITHUB_USERNAME`, `GITHUB_TOKEN`, `DOCKER_USERNAME`, `DOCKER_TOKEN`, and
  the six `AIRBAND_*` variables; also the commented-out `UAT_SDR_*` /
  `FR24_SHARING_KEY_UAT` lines. **Revoke** the GitHub and Docker Hub tokens at
  the provider; they were world-readable for months.
- `.env.example` rewritten to the live variable set.
- `rtl-airband/` removed from the working tree (history keeps it; the
  gitignored SDRplay `.run` installer is a re-downloadable vendor file).
- `.gitignore`: dropped the SDRplay patterns, added `.env.bak*`.

### Docs
- README rewritten: airband points to pluto-airband, WUD gone, bme680
  documented (topics, env vars, healthcheck, recovery), health/logging
  sections match reality, update + digest rollback procedure (rule 070),
  follow-ups listed. This CHANGELOG added.

### Apply
```bash
cd /home/pi/rfpi
docker compose -f docker-compose.yml config -q          # must be silent
docker compose images > ~/rfpi-images-2026-10-03.txt    # rule 070 record
docker tag bme680-mqtt:local bme680-mqtt:prev           # rollback tag
docker compose build bme680
docker compose up -d --remove-orphans                   # recreates all 11 containers
docker compose ps && docker compose logs --since=3m bme680 promtail
```
Expected: short ADS-B/MLAT gap while ultrafeeder recreates; feeders start
~60-120 s later once ultrafeeder reports healthy; MLAT resyncs within a few
minutes.

### Rollback
```bash
cd /home/pi/rfpi
git checkout -- docker-compose.yml promtail-config.yml bme680-mqtt/bme680_mqtt.py README.md .gitignore
cp -p .env.bak-2026-10-03 .env && chmod 600 .env
docker tag bme680-mqtt:prev bme680-mqtt:local
docker compose up -d --remove-orphans
```
(after the commit, `git revert` the commit instead of `git checkout`).

## 2026-06-28 → 2026-07-23 — uncommitted drift, committed 2026-10-03

Changes made on the host over the summer and left uncommitted for ~3 months
(reviewed in `REVIEW-2026-10-03.md` §5.5).

- **2026-06-28 bme680:** added `dew_point` (Magnus-Tetens) and `air_quality`
  (Pimoroni-style rolling gas baseline blended with humidity, 0-100); SENSORS
  became dicts with `state_class` / `icon` / friendly names; heartbeat moved
  into `touch_heartbeat()` and seeded at startup so the container no longer
  sits in "starting" for a full interval after boot.
- **2026-06-30 UAT/978 decommissioned:** removed the `dump978` service, the
  `adsb,dump978,30978,uat_in` feed and `ENABLE_978`/`URL_978` from
  ultrafeeder, piaware's UAT relay, rbfeeder's `UAT_RECEIVER_HOST` and fr24's
  `FR24KEY_UAT`; `.env` UAT values commented out (removed 2026-10-03).
- **2026-07 radar1090:** added the Radar1090 UK feeder behind the `radar1090`
  profile with tmpfs mounts and `RADAR1090_KEY` in `.env` (not yet keyed).
- **README:** dump978 rows removed, radar1090 row + usage added, title changed
  to "ADS-B (1090 MHz)".
- **.env:** site position/altitude/name and `MQTT_HOST` updated.
