# rfpi

Docker stack for the `rf-pi` Raspberry Pi 5: a 1090 MHz ADS-B receiver feeding
ten aggregators, a BME680 environmental sensor published to Home Assistant over
MQTT, and Promtail shipping container logs to a remote Loki.

The VHF airband scanner that used to live in this stack (`rtl-airband` +
SDRplay) has been retired. ATC audio now comes from the Pluto+ based receiver in
[pluto-airband](https://github.com/juchong/pluto-airband) (checked out at
`/home/pi/pluto-airband`), which runs on the host as `airband-feeds.service`
(see its `deploy/README.md`). Nothing airband-related
remains in this compose project.

## Services

### Core decoder

| Service | Image | Ports | Purpose |
|---------|-------|-------|---------|
| ultrafeeder | sdr-enthusiasts/docker-adsb-ultrafeeder | 8080, 9273-9274 | readsb (RTL-SDR), tar1090 map, graphs1090, MLAT hub, direct feeds to 10 aggregators |

### ADS-B feeders

All take Beast/SBS data from `ultrafeeder` and start only once it is healthy.

| Service | Image | Ports | Purpose |
|---------|-------|-------|---------|
| piaware | sdr-enthusiasts/docker-piaware | 8081 | FlightAware feeder |
| fr24 | sdr-enthusiasts/docker-flightradar24 | 8754 | FlightRadar24 feeder |
| pfclient | sdr-enthusiasts/docker-planefinder | 30053 | PlaneFinder feeder |
| rbfeeder | sdr-enthusiasts/docker-airnavradar | — | AirNav RadarBox feeder |
| planewatch | plane-watch/docker-plane-watch | — | Plane.watch feeder |
| adsbhub | sdr-enthusiasts/docker-adsbhub | — | ADSBHub feeder |
| opensky | sdr-enthusiasts/docker-opensky-network | — | OpenSky Network feeder |
| adsbexchange | sdr-enthusiasts/docker-adsbexchange | — | ADS-B Exchange feeder |
| radar1090 | sdr-enthusiasts/docker-radar1090 | — | Radar1090 UK feeder (opt-in via the `radar1090` profile; requires `RADAR1090_KEY`) |

### Environmental sensor

| Service | Image | Ports | Purpose |
|---------|-------|-------|---------|
| bme680 | `bme680-mqtt:local` (built from `bme680-mqtt/`) | — | BME680 temperature / humidity / pressure / dew point / gas / air quality to MQTT with Home Assistant discovery |

### Monitoring

| Service | Image | Ports | Purpose |
|---------|-------|-------|---------|
| promtail | grafana/promtail | — | Ships container logs to a remote Loki |

## Web interfaces

| URL | Service |
|-----|---------|
| `http://<host>:8080` | tar1090 map |
| `http://<host>:8080/graphs1090` | System statistics |
| `http://<host>:8081` | PiAware SkyAware |
| `http://<host>:8754` | FR24 status |
| `http://<host>:30053` | PlaneFinder client |
| `http://<host>:9273`, `:9274` | ultrafeeder Prometheus metrics |

## Aggregator feeds (via ultrafeeder)

adsb.fi, adsb.lol, airplanes.live, planespotters.net, theairtraffic.com,
avdelphi.com, hpradar.com, radarplane.com, flyitalyadsb.com, adsbexchange.com
(ADS-B + MLAT where offered), plus the dedicated feeder containers above.

## BME680 -> MQTT publisher (`bme680-mqtt/`)

A small Python service (`bme680_mqtt.py`, paho-mqtt 2.1, `smbus2`, Pimoroni
`bme680`) that reads the Bosch BME680 over I2C in userspace and publishes to
the house MQTT broker.

**Hardware:** sensor on I2C bus 1 (GPIO 2/3), address `0x77`; host needs
`dtparam=i2c_arm=on`. The container gets only `/dev/i2c-1`.

**Topics** (prefix `BME680_TOPIC_PREFIX`, default `rfpi/bme680`):

| Topic | Payload |
|-------|---------|
| `rfpi/bme680/state` | JSON every `BME680_INTERVAL` s: `temperature` (°C), `humidity` (%), `pressure` (hPa), `dew_point` (°C), `gas_resistance` (Ω, once the heater is stable), `air_quality` (0-100, higher = cleaner; rolling-baseline score blended with humidity) |
| `rfpi/bme680/availability` | retained `online` / `offline` (Last Will), re-asserted `online` every cycle |
| `homeassistant/sensor/rfpi_bme680/<key>/config` | retained HA discovery, one per measurement, with `expire_after = 3 x interval + 15 s` |
| `homeassistant/status` | *subscribed*: on HA's `online` birth message the publisher re-announces availability + discovery |

**Recovery behaviour** (review 2026-10-03 §2/§5):

- `connect_async` + `loop_start`, keepalive 30 s, reconnect backoff 1-15 s: a
  broker that is down at boot is retried, not crash-looped; paho's own
  diagnostics are logged to stdout at INFO and `on_disconnect` logs the reason.
- A cycle counts as successful only if the client is connected and the broker
  accepted the state publish. Only then is the heartbeat file
  `/tmp/bme680_healthy` touched, so the container healthcheck (heartbeat older
  than 90 s = unhealthy) reflects delivery, not just the read loop. After 10
  consecutive failed cycles the process exits 1 and `restart: unless-stopped`
  brings up a fresh one.

**Environment variables** (compose passes the first block from `.env`; the
rest fall back to in-script defaults unless added to the service's
`environment:`):

| Variable | Default | Purpose |
|----------|---------|---------|
| `MQTT_HOST` | *(required)* | broker host |
| `MQTT_PORT` | `1883` | broker port |
| `MQTT_USERNAME`, `MQTT_PASSWORD` | empty | broker credentials |
| `BME680_TOPIC_PREFIX` | `rfpi/bme680` | state/availability topic prefix |
| `BME680_INTERVAL` | `30` | seconds between readings |
| `BME680_I2C_ADDR` | `0x77` | sensor address |
| `BME680_I2C_BUS` | `1` | I2C bus number |
| `BME680_HA_DISCOVERY` | `true` | publish HA discovery configs |
| `BME680_MQTT_TLS` | `false` | TLS to the broker (system CA) |
| `BME680_HA_DISCOVERY_PREFIX` | `homeassistant` | HA discovery prefix |
| `BME680_HA_STATUS_TOPIC` | `<prefix>/status` | HA birth/will topic to watch |
| `BME680_NODE_ID` | `rfpi_bme680` | HA node id / MQTT client id |
| `BME680_DEVICE_NAME` | `RFPi BME680` | HA device name |
| `BME680_GAS_BASELINE_WINDOW` | `720` | samples in the gas baseline (6 h at 30 s) |
| `BME680_HUM_BASELINE` | `40.0` | ideal indoor RH % for the score |
| `BME680_HUM_WEIGHTING` | `0.25` | humidity share of the score |

**Rebuild after editing the script:**

```bash
# Keep a rollback tag for the running image, then rebuild and recreate
docker tag bme680-mqtt:local bme680-mqtt:prev
docker compose build bme680 && docker compose up -d bme680
docker compose logs --since=2m bme680
```

## Health checks

- **Upstream images (ultrafeeder + all feeders)** use their built-in
  `HEALTHCHECK` scripts: ultrafeeder checks that readsb refreshed
  `aircraft.json` within 60 s and that nginx/readsb/tar1090 have not died;
  feeders check an established TCP session to their aggregator and/or s6
  service death tallies. These are **not overridden** in compose (a `pgrep`
  test would match the s6 supervisor and hide a feeder stuck in an auth loop).
  The only override is ultrafeeder's probe *cadence* (60 s instead of
  upstream's 600 s) because the feeders gate on `service_healthy`.
- **bme680**: heartbeat file freshness (see above).
- **promtail**: `pgrep -x promtail` (image has no built-in check).

```bash
# Status at a glance
docker compose ps
# Why a container is unhealthy
docker inspect --format '{{json .State.Health}}' <container> | jq
```

## Logging

- Docker daemon default: `local` driver, 50 MB x 3 files per container
  (`/etc/docker/daemon.json`); no per-service logging blocks.
- Promtail discovers containers and streams their logs over the Docker socket
  (mounted read-only), keeps its read positions on the `promtail-positions`
  named volume so a restart does not re-ship history, and pushes to Loki over
  verified TLS (publicly trusted certificate) with basic auth.

**Labels in Grafana:** `host` (rf-pi), `container`, `service` (compose
service), `project`.

```logql
{host="rf-pi"}
{host="rf-pi", container="ultrafeeder"} |= "error"
{host="rf-pi", service="bme680"} |= "WARNING"
```

## Usage

```bash
cd /home/pi/rfpi

# Validate before any change
docker compose -f docker-compose.yml config -q

# Start / apply the stack (only changed services are recreated)
docker compose up -d

# Opt-in Radar1090 UK feeder (set RADAR1090_KEY in .env first)
docker compose --profile radar1090 up -d radar1090

# Status, logs
docker compose ps
docker compose logs --since=10m <service>
```

## Updating images (and rolling back)

All images are `:latest`, so every pull can change behaviour. Follow
`.cursor/rules/070-Backups-and-Rollback.mdc`: record the old -> new image map
before pulling and keep a digest-pinned rollback path.

```bash
cd /home/pi/rfpi

# 1. Record what is running (tags, image ids, repo digests) before pulling
docker compose images | tee ~/rfpi-images-$(date +%F-%H%M%S).txt
docker image inspect --format '{{.RepoTags}} {{.RepoDigests}}' $(docker compose images -q) \
  | tee -a ~/rfpi-images-$(date +%F-%H%M%S).txt

# 2. Pull and recreate only the services whose image changed
docker compose pull && docker compose up -d

# 3. Post-checks
docker compose ps
docker compose logs --since=5m
```

**Rollback one service by digest.** The previous image stays on disk until
pruned. Pin it in a `docker-compose.override.yml` (gitignored) and recreate:

```yaml
services:
  piaware:
    image: ghcr.io/sdr-enthusiasts/docker-piaware@sha256:<digest from step 1>
```

```bash
docker compose up -d piaware
```

Remove the override once upstream is fixed. Do not `docker image prune` until
the new images have run cleanly for a while.

## Environment variables

`.env` is git-crypt encrypted in the repository, plaintext mode 600 in the
working tree, and contains **only** variables referenced by
`docker-compose.yml` / `promtail-config.yml`. `.env.example` lists them all
with placeholders:

| Group | Variables |
|-------|-----------|
| Site identity | `FEEDER_NAME`, `FEEDER_LAT`, `FEEDER_LONG`, `FEEDER_ALT_M`, `FEEDER_TZ`, `ULTRAFEEDER_UUID`, `FEEDER_HEYWHATSTHAT_ID`, `FEEDER_HEYWHATSTHAT_ALTS` |
| RTL-SDR | `ADSB_SDR_SERIAL`, `ADSB_SDR_GAIN`, `ADSB_SDR_PPM` |
| Aggregator keys | `PIAWARE_FEEDER_ID`, `FR24_SHARING_KEY`, `PLANEFINDER_SHARECODE`, `AIRNAVRADAR_SHARING_KEY`, `PW_API_KEY`, `ADSBHUB_STATION_KEY`, `OPENSKY_USERNAME`, `OPENSKY_SERIAL`, `RADAR1090_KEY` |
| Loki | `LOKI_URL`, `LOKI_USERNAME`, `LOKI_PASSWORD`, `LOKI_TENANT_ID` |
| BME680 | `MQTT_HOST`, `MQTT_PORT`, `MQTT_USERNAME`, `MQTT_PASSWORD`, `BME680_TOPIC_PREFIX`, `BME680_INTERVAL`, `BME680_I2C_ADDR`, `BME680_HA_DISCOVERY` |

## git-crypt

**Unlock on a new machine:**
```bash
git clone <repo>
git-crypt unlock /path/to/git-crypt-key-rfpi.key
chmod 600 .env
```

**Check encryption status:**
```bash
git-crypt status
```

## Directory structure

```
rfpi/
├── docker-compose.yml       # the stack (validate: docker compose config -q)
├── .env                     # secrets (git-crypt encrypted; mode 600)
├── .env.example             # placeholder template (plaintext)
├── .gitattributes           # git-crypt config
├── promtail-config.yml      # log shipping config
├── CHANGELOG.md             # operational change log (rule 030 step 6)
├── bme680-mqtt/
│   ├── Dockerfile           # python:3.11-slim + smbus2 + paho-mqtt + bme680
│   ├── requirements.txt
│   └── bme680_mqtt.py       # the publisher
└── .cursor/rules/           # operating conventions for this host
```

## Follow-ups (known deviations from `.cursor/rules`)

- Ports are published on `0.0.0.0` and there is no named network / reverse
  proxy; the host is LAN-only today. Decide on bind addresses once the access
  pattern is known.
- No memory limits yet: the memory cgroup is disabled on this host
  (`cgroup_disable=memory`) until the next reboot. Add `mem_limit` after that.
- Images are `:latest`; either pin dated tags or schedule the update procedure
  above.
