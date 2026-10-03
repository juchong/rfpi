#!/usr/bin/env python3
"""Read a Bosch BME680 over I2C and publish readings to MQTT.

Publishes a single JSON state message per cycle plus (optionally) Home
Assistant MQTT discovery config so the sensors appear automatically. An
availability topic with a Last Will message reports online/offline.

Connection handling follows the usual HA-publisher pattern: paho's network
thread owns the connection (connect_async + loop_start) and retries with a
bounded backoff, availability + discovery are re-announced on every
(re)connect and on Home Assistant's birth message, and the healthcheck
heartbeat is only refreshed when a state publish was accepted on a live
connection.
"""

import collections
import json
import logging
import math
import os
import signal
import sys
import time

import bme680
import paho.mqtt.client as mqtt
from smbus2 import SMBus


def env(key, default=None, required=False):
    val = os.environ.get(key, default)
    if required and (val is None or val == ""):
        log(f"FATAL: required env var {key} is not set")
        sys.exit(1)
    return val


def log(msg):
    print(f"{time.strftime('%Y-%m-%dT%H:%M:%S%z')} {msg}", flush=True)


# --- Configuration -----------------------------------------------------------
MQTT_HOST = env("MQTT_HOST", required=True)
MQTT_PORT = int(env("MQTT_PORT", "1883"))
MQTT_USERNAME = env("MQTT_USERNAME", "")
MQTT_PASSWORD = env("MQTT_PASSWORD", "")
MQTT_TLS = env("BME680_MQTT_TLS", "false").lower() == "true"

TOPIC_PREFIX = env("BME680_TOPIC_PREFIX", "rfpi/bme680").rstrip("/")
INTERVAL = int(env("BME680_INTERVAL", "30"))
I2C_ADDR = int(env("BME680_I2C_ADDR", "0x77"), 16)
I2C_BUS = int(env("BME680_I2C_BUS", "1"))
HA_DISCOVERY = env("BME680_HA_DISCOVERY", "true").lower() == "true"
HA_PREFIX = env("BME680_HA_DISCOVERY_PREFIX", "homeassistant").rstrip("/")
# Home Assistant publishes "online" here when it (re)starts (its birth
# message); we re-announce availability + discovery when we see it so a
# restarted HA rediscovers us without waiting for our next reconnect.
HA_STATUS_TOPIC = env("BME680_HA_STATUS_TOPIC", f"{HA_PREFIX}/status")

NODE_ID = env("BME680_NODE_ID", "rfpi_bme680")
DEVICE_NAME = env("BME680_DEVICE_NAME", "RFPi BME680")

# Air-quality tuning. The BME680 reports gas *resistance* (Ω), which rises in
# clean air and falls with VOCs. We turn that into a 0-100 score (higher =
# cleaner) relative to a rolling baseline, blended with humidity, following the
# well-known Pimoroni indoor-air-quality approach.
GAS_BASELINE_WINDOW = int(env("BME680_GAS_BASELINE_WINDOW", "720"))  # samples
HUM_BASELINE = float(env("BME680_HUM_BASELINE", "40.0"))  # ideal indoor RH %
HUM_WEIGHTING = float(env("BME680_HUM_WEIGHTING", "0.25"))  # humidity share

STATE_TOPIC = f"{TOPIC_PREFIX}/state"
AVAILABILITY_TOPIC = f"{TOPIC_PREFIX}/availability"
HEARTBEAT_FILE = "/tmp/bme680_healthy"

# Broker declares us dead (and publishes the LWT) after 1.5x this many seconds
# of silence; 30 s keeps the HA "unavailable" lag short after a crash.
MQTT_KEEPALIVE = 30
# HA marks each sensor "unavailable" if no state arrives within this window:
# three missed cycles plus slack for a reconnect.
EXPIRE_AFTER = INTERVAL * 3 + 15
# Consecutive failed publish cycles before exiting 1 so Docker's restart policy
# gives us a fresh process. The heartbeat stops refreshing on the first
# failure, so the container healthcheck flags the problem well before this.
MAX_PUBLISH_FAILURES = 10

# json key / HA device_class / unit / icon / state_class / friendly name.
# device_class and icon are mutually exclusive in HA; use device_class where a
# standard one exists, otherwise an icon.
SENSORS = [
    {"key": "temperature", "device_class": "temperature", "unit": "°C", "state_class": "measurement"},
    {"key": "humidity", "device_class": "humidity", "unit": "%", "state_class": "measurement"},
    {"key": "pressure", "device_class": "pressure", "unit": "hPa", "state_class": "measurement"},
    {"key": "dew_point", "device_class": "temperature", "unit": "°C", "state_class": "measurement", "name": "Dew Point"},
    {"key": "gas_resistance", "unit": "Ω", "icon": "mdi:radiator", "state_class": "measurement"},
    {"key": "air_quality", "unit": "%", "icon": "mdi:air-filter", "state_class": "measurement", "name": "Air Quality"},
]


def configure_sensor():
    try:
        sensor = bme680.BME680(I2C_ADDR, SMBus(I2C_BUS))
    except (RuntimeError, IOError) as exc:
        log(f"FATAL: could not open BME680 at {hex(I2C_ADDR)} on bus {I2C_BUS}: {exc}")
        sys.exit(1)

    sensor.set_humidity_oversample(bme680.OS_2X)
    sensor.set_pressure_oversample(bme680.OS_4X)
    sensor.set_temperature_oversample(bme680.OS_8X)
    sensor.set_filter(bme680.FILTER_SIZE_3)
    sensor.set_gas_status(bme680.ENABLE_GAS_MEAS)
    sensor.set_gas_heater_temperature(320)
    sensor.set_gas_heater_duration(150)
    sensor.select_gas_heater_profile(0)
    log(f"BME680 initialised at {hex(I2C_ADDR)}")
    return sensor


def make_paho_logger():
    """Route paho's own diagnostics (socket errors, reconnect attempts) to
    stdout in the same timestamped style as log(). INFO hides paho's
    per-packet DEBUG chatter (PINGREQ/PINGRESP, every PUBLISH)."""
    logger = logging.getLogger("paho.mqtt.client")
    logger.setLevel(logging.INFO)
    logger.propagate = False
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(
            logging.Formatter("%(asctime)s paho: %(message)s", "%Y-%m-%dT%H:%M:%S%z")
        )
        logger.addHandler(handler)
    return logger


def make_client():
    client = mqtt.Client(
        mqtt.CallbackAPIVersion.VERSION2, client_id=NODE_ID
    )
    if MQTT_USERNAME:
        client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)
    if MQTT_TLS:
        client.tls_set()
    client.will_set(AVAILABILITY_TOPIC, "offline", qos=1, retain=True)
    client.enable_logger(make_paho_logger())
    # Reconnect backoff 1 s -> 15 s. paho's default caps at 120 s, which is a
    # long "unavailable" gap in HA after a brief broker blip.
    client.reconnect_delay_set(min_delay=1, max_delay=15)

    def on_connect(c, userdata, flags, reason_code, properties):
        if reason_code == 0:
            log(f"Connected to MQTT {MQTT_HOST}:{MQTT_PORT}")
            announce(c)
            c.subscribe(HA_STATUS_TOPIC, qos=1)
        else:
            log(f"MQTT connect failed: {reason_code}")

    def on_disconnect(c, userdata, flags, reason_code, properties):
        if reason_code == 0:
            log("Disconnected from MQTT (clean)")
            return
        origin = (
            "broker closed the connection"
            if flags.is_disconnect_packet_from_server
            else "connection lost"
        )
        log(f"Disconnected from MQTT ({origin}): {reason_code}; reconnecting with 1-15 s backoff")

    def on_message(c, userdata, msg):
        if msg.topic != HA_STATUS_TOPIC:
            return
        payload = msg.payload.decode(errors="replace").strip()
        if payload == "online":
            log("Home Assistant birth message received; re-announcing")
            announce(c)
        else:
            log(f"Home Assistant status: {payload}")

    client.on_connect = on_connect
    client.on_disconnect = on_disconnect
    client.on_message = on_message
    return client


def announce(client):
    """Assert availability (retained) and, if enabled, HA discovery.

    Called on every (re)connect and on HA's birth message, so neither a broker
    restart nor an HA restart leaves us stuck behind a stale retained
    'offline' or a forgotten discovery config.
    """
    client.publish(AVAILABILITY_TOPIC, "online", qos=1, retain=True)
    if HA_DISCOVERY:
        publish_discovery(client)


def publish_discovery(client):
    device = {
        "identifiers": [NODE_ID],
        "name": DEVICE_NAME,
        "model": "BME680",
        "manufacturer": "Bosch",
    }
    for sensor in SENSORS:
        key = sensor["key"]
        config = {
            "name": sensor.get("name", key.replace("_", " ").title()),
            "unique_id": f"{NODE_ID}_{key}",
            "state_topic": STATE_TOPIC,
            "availability_topic": AVAILABILITY_TOPIC,
            "value_template": f"{{{{ value_json.{key} }}}}",
            "unit_of_measurement": sensor["unit"],
            "expire_after": EXPIRE_AFTER,
            "device": device,
        }
        if sensor.get("device_class"):
            config["device_class"] = sensor["device_class"]
        if sensor.get("state_class"):
            config["state_class"] = sensor["state_class"]
        if sensor.get("icon"):
            config["icon"] = sensor["icon"]
        topic = f"{HA_PREFIX}/sensor/{NODE_ID}/{key}/config"
        client.publish(topic, json.dumps(config), qos=1, retain=True)
    log("Published Home Assistant discovery config")


def publish_state(client, payload):
    """Publish one state message, plus a retained availability refresh.

    Returns True only when the client is connected and paho accepted the
    state message for the live socket, so the caller can tie the healthcheck
    heartbeat to real delivery rather than to the read loop still spinning.
    """
    if not client.is_connected():
        log("WARNING: not connected to MQTT; state not published")
        return False
    # Re-assert availability every cycle so a retained 'offline' left behind
    # by the LWT during a reconnect race is corrected within one interval.
    client.publish(AVAILABILITY_TOPIC, "online", qos=1, retain=True)
    info = client.publish(STATE_TOPIC, json.dumps(payload), qos=0, retain=False)
    if info.rc != mqtt.MQTT_ERR_SUCCESS:
        log(f"WARNING: state publish rejected: {mqtt.error_string(info.rc)}")
        return False
    log(f"Published: {payload}")
    return True


def touch_heartbeat():
    try:
        with open(HEARTBEAT_FILE, "w") as fh:
            fh.write(str(int(time.time())))
    except OSError:
        pass


def dew_point(temp_c, humidity):
    """Dew point in °C via the Magnus-Tetens approximation."""
    a, b = 17.62, 243.12
    gamma = (a * temp_c) / (b + temp_c) + math.log(max(humidity, 1e-3) / 100.0)
    return (b * gamma) / (a - gamma)


class AirQuality:
    """Convert raw gas resistance + humidity into a 0-100 air-quality score.

    The gas baseline is the mean of a rolling window of recent readings (clean
    air reads high), so the score reflects deviation from the local baseline
    rather than an absolute calibration. Higher score = cleaner air.
    """

    def __init__(self, window=GAS_BASELINE_WINDOW, hum_baseline=HUM_BASELINE,
                 hum_weighting=HUM_WEIGHTING):
        self.gas_readings = collections.deque(maxlen=max(window, 1))
        self.hum_baseline = hum_baseline
        self.hum_weighting = max(0.0, min(hum_weighting, 1.0))

    def score(self, gas_resistance, humidity):
        self.gas_readings.append(gas_resistance)
        gas_baseline = sum(self.gas_readings) / len(self.gas_readings)

        hum_offset = humidity - self.hum_baseline
        if hum_offset > 0:
            hum_score = (100 - self.hum_baseline - hum_offset) / (100 - self.hum_baseline)
        else:
            hum_score = (self.hum_baseline + hum_offset) / self.hum_baseline
        hum_score = max(0.0, hum_score) * self.hum_weighting * 100

        gas_weight = (1 - self.hum_weighting) * 100
        if gas_baseline > 0 and gas_resistance < gas_baseline:
            gas_score = (gas_resistance / gas_baseline) * gas_weight
        else:
            gas_score = gas_weight

        return round(hum_score + gas_score, 1)


def read_payload(sensor):
    if not sensor.get_sensor_data():
        return None
    temperature = round(sensor.data.temperature, 2)
    humidity = round(sensor.data.humidity, 2)
    payload = {
        "temperature": temperature,
        "pressure": round(sensor.data.pressure, 2),
        "humidity": humidity,
        "dew_point": round(dew_point(temperature, humidity), 2),
    }
    if sensor.data.heat_stable:
        payload["gas_resistance"] = round(sensor.data.gas_resistance)
    return payload


def main():
    running = {"flag": True}

    def shutdown(signum, _frame):
        log(f"Received signal {signum}, shutting down")
        running["flag"] = False

    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)

    sensor = configure_sensor()
    air_quality = AirQuality()
    client = make_client()
    # connect_async hands the connect to the network thread, which keeps
    # retrying with the configured backoff if the broker is unreachable at
    # boot; a synchronous connect() would raise and crash-loop the container.
    client.connect_async(MQTT_HOST, MQTT_PORT, keepalive=MQTT_KEEPALIVE)
    client.loop_start()

    # Seed the heartbeat at startup so the healthcheck treats the process as
    # live immediately; the first BME680 read after init typically returns no
    # data (gas heater not yet stable), which would otherwise leave the
    # container stuck in "starting" for a full INTERVAL.
    touch_heartbeat()
    failed_cycles = 0

    try:
        while running["flag"]:
            payload = read_payload(sensor)
            if payload is None:
                log("No sensor data this cycle")
            else:
                if "gas_resistance" in payload:
                    payload["air_quality"] = air_quality.score(
                        payload["gas_resistance"], payload["humidity"]
                    )
                if publish_state(client, payload):
                    failed_cycles = 0
                    touch_heartbeat()
                else:
                    failed_cycles += 1
                    log(f"WARNING: {failed_cycles}/{MAX_PUBLISH_FAILURES} consecutive publish failures; heartbeat not refreshed")
                    if failed_cycles >= MAX_PUBLISH_FAILURES:
                        log("FATAL: giving up after repeated publish failures; exiting so the container restarts")
                        sys.exit(1)
            for _ in range(INTERVAL):
                if not running["flag"]:
                    break
                time.sleep(1)
    finally:
        client.publish(AVAILABILITY_TOPIC, "offline", qos=1, retain=True)
        client.loop_stop()
        client.disconnect()
        log("Stopped")


if __name__ == "__main__":
    main()
