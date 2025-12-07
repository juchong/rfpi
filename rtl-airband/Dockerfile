# RTLSDR-Airband with SDRPlay support
# Builds SoapySDRPlay module from source to match container's SoapySDR ABI
#
# IMPORTANT: SDRPlay requires:
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

# Copy SDRPlay API library (built for aarch64/ARM64)
COPY sdrplay/libsdrplay_api.so.3.15 /usr/local/lib/
RUN ln -sf /usr/local/lib/libsdrplay_api.so.3.15 /usr/local/lib/libsdrplay_api.so.3 && \
    ln -sf /usr/local/lib/libsdrplay_api.so.3 /usr/local/lib/libsdrplay_api.so && \
    ldconfig

# Copy SDRPlay API headers (needed for build)
COPY sdrplay/sdrplay_api*.h /usr/local/include/

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
