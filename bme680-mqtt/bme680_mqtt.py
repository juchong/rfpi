#!/usr/bin/env python3
"""Read a Bosch BME680 over I2C and publish readings to MQTT.

Publishes a single JSON state message per cycle plus (optionally) Home
Assistant MQTT discovery config so the sensors appear automatically. An
availability topic with a Last Will message reports online/offline.
"""

import json
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

NODE_ID = env("BME680_NODE_ID", "rfpi_bme680")
DEVICE_NAME = env("BME680_DEVICE_NAME", "RFPi BME680")

STATE_TOPIC = f"{TOPIC_PREFIX}/state"
AVAILABILITY_TOPIC = f"{TOPIC_PREFIX}/availability"
HEARTBEAT_FILE = "/tmp/bme680_healthy"

# device_class / unit / json key for each measurement
SENSORS = [
    ("temperature", "temperature", "°C", "mdi:thermometer"),
    ("humidity", "humidity", "%", "mdi:water-percent"),
    ("pressure", "pressure", "hPa", "mdi:gauge"),
    ("gas_resistance", None, "Ω", "mdi:radiator"),
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


def make_client():
    client = mqtt.Client(
        mqtt.CallbackAPIVersion.VERSION2, client_id=NODE_ID
    )
    if MQTT_USERNAME:
        client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)
    if MQTT_TLS:
        client.tls_set()
    client.will_set(AVAILABILITY_TOPIC, "offline", qos=1, retain=True)

    def on_connect(c, userdata, flags, reason_code, properties):
        if reason_code == 0:
            log(f"Connected to MQTT {MQTT_HOST}:{MQTT_PORT}")
            c.publish(AVAILABILITY_TOPIC, "online", qos=1, retain=True)
            if HA_DISCOVERY:
                publish_discovery(c)
        else:
            log(f"MQTT connect failed: {reason_code}")

    client.on_connect = on_connect
    return client


def publish_discovery(client):
    device = {
        "identifiers": [NODE_ID],
        "name": DEVICE_NAME,
        "model": "BME680",
        "manufacturer": "Bosch",
    }
    for key, device_class, unit, icon in SENSORS:
        config = {
            "name": key.replace("_", " ").title(),
            "unique_id": f"{NODE_ID}_{key}",
            "state_topic": STATE_TOPIC,
            "availability_topic": AVAILABILITY_TOPIC,
            "value_template": f"{{{{ value_json.{key} }}}}",
            "unit_of_measurement": unit,
            "device": device,
        }
        if device_class:
            config["device_class"] = device_class
            config["state_class"] = "measurement"
        else:
            config["icon"] = icon
        topic = f"{HA_PREFIX}/sensor/{NODE_ID}/{key}/config"
        client.publish(topic, json.dumps(config), qos=1, retain=True)
    log("Published Home Assistant discovery config")


def read_payload(sensor):
    if not sensor.get_sensor_data():
        return None
    payload = {
        "temperature": round(sensor.data.temperature, 2),
        "pressure": round(sensor.data.pressure, 2),
        "humidity": round(sensor.data.humidity, 2),
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
    client = make_client()
    client.connect(MQTT_HOST, MQTT_PORT, keepalive=60)
    client.loop_start()

    try:
        while running["flag"]:
            payload = read_payload(sensor)
            if payload is None:
                log("No sensor data this cycle")
            else:
                client.publish(STATE_TOPIC, json.dumps(payload), qos=0, retain=False)
                log(f"Published: {payload}")
                try:
                    with open(HEARTBEAT_FILE, "w") as fh:
                        fh.write(str(int(time.time())))
                except OSError:
                    pass
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
