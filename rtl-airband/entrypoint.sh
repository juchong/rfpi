#!/bin/sh
set -e

# Generate config from template using environment variables
envsubst < /app/rtl_airband.conf.template > /app/rtl_airband.conf

# Execute rtl_airband
exec /app/rtl_airband -F -e -c /app/rtl_airband.conf

