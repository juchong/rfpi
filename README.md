# rfpi

Dockerized ADS-B/UAT feeder stack for Raspberry Pi.

## Services

| Service | Image | Ports | Purpose |
|---------|-------|-------|---------|
| ultrafeeder | sdr-enthusiasts/docker-adsb-ultrafeeder | 8080, 9273-9274 | Core decoder, tar1090 map, MLAT hub |
| dump978 | sdr-enthusiasts/docker-dump978 | 30980 | UAT (978MHz) decoder |
| piaware | sdr-enthusiasts/docker-piaware | 8081 | FlightAware feeder |
| fr24 | sdr-enthusiasts/docker-flightradar24 | 8754 | FlightRadar24 feeder |
| pfclient | sdr-enthusiasts/docker-planefinder | 30053 | PlaneFinder feeder |
| planewatch | plane-watch/docker-plane-watch | — | Plane.watch feeder |
| rbfeeder | sdr-enthusiasts/docker-airnavradar | — | AirNav RadarBox feeder |
| adsbhub | sdr-enthusiasts/docker-adsbhub | — | ADSBHub feeder |
| opensky | sdr-enthusiasts/docker-opensky-network | — | OpenSky Network feeder |
| adsbexchange | sdr-enthusiasts/docker-adsbexchange | — | ADS-B Exchange feeder |
| wud | fmartinou/whats-up-docker | 3000 | Container update manager |

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

## Web Interfaces

| URL | Service |
|-----|---------|
| `http://<host>:8080` | tar1090 map + graphs1090 |
| `http://<host>:8080/graphs1090` | System statistics |
| `http://<host>:8081` | PiAware SkyAware |
| `http://<host>:8754` | FR24 status |
| `http://<host>:3000` | WUD dashboard |
| `http://<host>:30053` | PlaneFinder client |
| `http://<host>:30980` | dump978 SkyAware978 |

## Usage

```bash
# Start all services
sudo docker compose up -d

# View logs
sudo docker compose logs -f <service>

# Check status
sudo docker compose ps
```

## Environment Variables

Requires `.env` file with feeder credentials and location data. See `.env.example` if available.
