# rfpi

Dockerized ADS-B/UAT feeder stack and ATC airband scanner for Raspberry Pi.

## Services

### Core Decoders

| Service | Image | Ports | Purpose |
|---------|-------|-------|---------|
| ultrafeeder | sdr-enthusiasts/docker-adsb-ultrafeeder | 8080, 9273-9274 | ADS-B decoder, tar1090 map, MLAT hub |
| dump978 | sdr-enthusiasts/docker-dump978 | 30980 | UAT (978MHz) decoder |

### ADS-B Feeders

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

### Airband Scanner

| Service | Image | Ports | Purpose |
|---------|-------|-------|---------|
| rtl-airband | rtlsdr-airband-sdrplay:local | — | ATC audio streaming to Icecast/LiveATC |

Streams 17 KSEA/KRNT aviation frequencies using SDRPlay RSPduo.

**Host requirements:**
- SDRPlay API service running: `systemctl enable --now sdrplay`
- USB device access and `/dev/shm` for shared memory IPC

**Build setup:**

1. Download SDRPlay API (Linux x64/ARM32/ARM64) from [sdrplay.com/api](https://www.sdrplay.com/api/)
2. Place the `.run` file in `rtl-airband/sdrplay/`:
   ```bash
   cp ~/Downloads/SDRplay_RSP_API-Linux-*.run rtl-airband/sdrplay/
   ```
3. Build and start:
   ```bash
   docker compose build rtl-airband
   docker compose up -d rtl-airband
   ```

The Dockerfile extracts the correct architecture automatically. Requires API 3.15+ for RSPduo/RSPdx-R2 support.

### Monitoring & Utilities

| Service | Image | Ports | Purpose |
|---------|-------|-------|---------|
| promtail | grafana/promtail | — | Ships Docker logs to Loki |
| wud | fmartinou/whats-up-docker | 3000 | Container update manager |

## Web Interfaces

| URL | Service |
|-----|---------|
| `http://<host>:8080` | tar1090 map |
| `http://<host>:8080/graphs1090` | System statistics |
| `http://<host>:8081` | PiAware SkyAware |
| `http://<host>:8754` | FR24 status |
| `http://<host>:3000` | WUD dashboard |
| `http://<host>:30053` | PlaneFinder client |
| `http://<host>:30980` | dump978 SkyAware978 |

## Aggregator Feeds (via ultrafeeder)

- adsb.fi
- adsb.lol
- airplanes.live
- planespotters.net
- theairtraffic.com
- avdelphi.com
- hpradar.com
- radarplane.com
- flyitalyadsb.com
- adsbexchange.com

## Health Checks

All containers include Docker health checks:
- **HTTP checks** for web services (ultrafeeder, dump978, piaware, fr24, pfclient, wud)
- **Process checks** for feeders (rtl-airband, rbfeeder, planewatch, adsbhub, opensky, adsbexchange)
- **Interval:** 60s | **Timeout:** 10s | **Retries:** 3

Check health status:
```bash
docker ps --format 'table {{.Names}}\t{{.Status}}'
```

## Log Aggregation

Promtail ships all container logs to a remote Loki server.

**Labels available in Grafana:**
- `host` — Pi hostname (rf-pi)
- `container` — Container name
- `service` — Compose service name

**Example queries:**
```logql
{host="rf-pi"}
{host="rf-pi", container="rtl-airband"}
{host="rf-pi"} |= "error"
```

## Usage

```bash
# Start all services
docker compose up -d

# Start specific service
docker compose up -d rtl-airband

# View logs
docker compose logs -f rtl-airband

# Check status
docker compose ps

# Restart after config change
docker compose restart rtl-airband

# Rebuild custom image
docker compose build rtl-airband
```

## Environment Variables

The `.env` file is encrypted with git-crypt. Required variables:

```bash
# Feeder identity
FEEDER_NAME=
FEEDER_LAT=
FEEDER_LONG=
FEEDER_ALT_M=
FEEDER_TZ=

# SDR configuration
ADSB_SDR_SERIAL=
ADSB_SDR_GAIN=
UAT_SDR_SERIAL=

# Airband streaming
AIRBAND_ICECAST_SERVER=
AIRBAND_ICECAST_PORT=
AIRBAND_ICECAST_PASSWORD=
AIRBAND_LIVEATC_SERVER=
AIRBAND_LIVEATC_PORT=
AIRBAND_LIVEATC_PASSWORD=

# Log aggregation
LOKI_URL=
LOKI_USERNAME=
LOKI_PASSWORD=

# Feeder keys (various aggregators)
# See .env for full list
```

## git-crypt

The `.env` file is encrypted in the repository.

**Unlock on a new machine:**
```bash
git clone <repo>
git-crypt unlock /path/to/git-crypt-key-rfpi.key
```

**Check encryption status:**
```bash
git-crypt status
```

## Directory Structure

```
rfpi/
├── docker-compose.yml
├── .env                    # Encrypted secrets
├── .gitattributes          # git-crypt config
├── promtail-config.yml     # Log shipping config
└── rtl-airband/
    ├── Dockerfile          # Custom image (downloads SDRPlay API)
    ├── entrypoint.sh       # Config templating
    └── config/
        └── rtl_airband.conf.template
```
