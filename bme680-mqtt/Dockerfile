# BME680 -> MQTT publisher
#
# Reads the Bosch BME680 over I2C (userspace, via smbus2) and publishes
# temperature/humidity/pressure/gas to MQTT with Home Assistant discovery.
#
# RUNTIME REQUIREMENTS:
# 1. Host I2C enabled (dtparam=i2c_arm=on) and sensor wired to bus 1 (GPIO2/3).
# 2. Container needs the I2C bus device: --device=/dev/i2c-1
# 3. Broker connection supplied via environment (see .env).

FROM python:3.11-slim-bookworm

ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt /app/requirements.txt
# Install smbus2 + paho first, then bme680 without its legacy `smbus` dep
# (we pass it an smbus2 bus object at runtime instead - no C toolchain needed).
RUN pip install --no-cache-dir -r /app/requirements.txt && \
    pip install --no-cache-dir --no-deps bme680==1.1.1

COPY bme680_mqtt.py /app/bme680_mqtt.py

ENTRYPOINT ["python", "/app/bme680_mqtt.py"]
