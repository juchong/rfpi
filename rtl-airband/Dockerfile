# RTLSDR-Airband with SDRPlay support
# Installs SDRPlay API from .run file and builds SoapySDRPlay from source
#
# PREREQUISITES:
# 1. Download SDRPlay API installer from https://www.sdrplay.com/api/
# 2. Place the .run file in rtl-airband/sdrplay/ folder
#
# RUNTIME REQUIREMENTS:
# 1. sdrplay_apiService running on the HOST (not in container)
# 2. /dev/shm mounted into container for shared memory IPC
# 3. USB device access via --device=/dev/bus/usb

FROM ghcr.io/rtl-airband/rtlsdr-airband:latest

# Install build dependencies and envsubst (for config templating)
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
      build-essential \
      cmake \
      git \
      ca-certificates \
      libsoapysdr-dev \
      gettext-base \
      && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Copy and extract SDRPlay API installer
COPY sdrplay/*.run /tmp/sdrplay_api.run
RUN chmod +x /tmp/sdrplay_api.run && \
    cd /tmp && \
    ./sdrplay_api.run --tar -xf && \
    # Select correct architecture
    ARCH=$(uname -m) && \
    if [ "$ARCH" = "aarch64" ]; then \
      LIB_DIR="arm64"; \
    elif [ "$ARCH" = "armv7l" ]; then \
      LIB_DIR="armhf"; \
    else \
      LIB_DIR="amd64"; \
    fi && \
    echo "Installing SDRPlay API for architecture: $LIB_DIR" && \
    cp /tmp/${LIB_DIR}/libsdrplay_api.so.* /usr/local/lib/ && \
    cp /tmp/inc/*.h /usr/local/include/ && \
    cd /usr/local/lib && \
    ln -sf libsdrplay_api.so.* libsdrplay_api.so.3 && \
    ln -sf libsdrplay_api.so.3 libsdrplay_api.so && \
    ldconfig && \
    rm -rf /tmp/sdrplay_api.run /tmp/arm* /tmp/amd64 /tmp/inc /tmp/*.sh /tmp/*.txt

# Build SoapySDRPlay from source (matches container's SoapySDR ABI)
RUN git clone https://github.com/pothosware/SoapySDRPlay.git /tmp/SoapySDRPlay && \
    cd /tmp/SoapySDRPlay && \
    mkdir build && cd build && \
    cmake .. && \
    make -j$(nproc) && \
    make install && \
    ldconfig && \
    rm -rf /tmp/SoapySDRPlay

# Copy entrypoint script (handles config templating)
COPY entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

# Override default command with our entrypoint
ENTRYPOINT ["/usr/bin/tini", "--", "/app/entrypoint.sh"]
CMD []
