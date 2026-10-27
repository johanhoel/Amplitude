# Stage 1: Builder
# Same Debian release as the runtime stage, so the binaries' glibc matches
FROM rust:1-bookworm AS builder

RUN apt-get update && apt-get install -y \
    build-essential \
    cmake \
    git \
    pkg-config \
    libasound2-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build

# Clone and build Virgil (virgild + ALSA plugin; no GTK control app, no tests)
RUN git clone --depth 1 https://github.com/Audbol/virgil-virtual-soundcard.git virgil && \
    cd virgil && \
    mkdir build && cd build && \
    cmake .. -DCMAKE_BUILD_TYPE=Release \
      -DVIRGIL_BUILD_ASIO=OFF \
      -DVIRGIL_BUILD_COREAUDIO=OFF \
      -DVIRGIL_BUILD_ALSA=ON \
      -DVIRGIL_BUILD_GTK_CONTROL=OFF \
      -DVIRGIL_BUILD_TESTS=OFF && \
    cmake --build . -j $(nproc)

# Stage 2: Runtime
FROM debian:bookworm-slim

RUN apt-get update && apt-get install -y \
    libasound2 \
    curl \
    ca-certificates \
    alsa-utils \
    dbus \
    avahi-daemon \
    avahi-utils \
    libavahi-client3 \
    libavahi-core7 \
    && rm -rf /var/lib/apt/lists/*

# Install Shairport-sync (AirPlay receiver)
RUN apt-get update && apt-get install -y \
    shairport-sync \
    && rm -rf /var/lib/apt/lists/*

# Install Snapcast (Google Cast receiver)
RUN apt-get update && apt-get install -y \
    snapclient \
    snapserver \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy built Dante engine from Virgil (base library)
COPY --from=builder /build/virgil/build/virgild /app/
COPY --from=builder /build/virgil/build/drivers/alsa/libasound_module_pcm_virgil.so /usr/lib/x86_64-linux-gnu/alsa-lib/

# Copy config templates
COPY --from=builder /build/virgil/packaging/virgil.conf /app/virgil.conf.template
COPY config/shairport-sync.conf /app/shairport-sync.conf.template
COPY config/snapserver.conf /app/snapserver.conf.template
COPY config/asound.conf /etc/asound.conf

# Create non-root user
RUN useradd -m -s /bin/bash dante

# Expose ports
# Dante: 319/320 (PTP), 5353 (mDNS), 4440/4455/8700/8800 (control), multicast (audio)
EXPOSE 319/udp 320/udp 4440 4455 8700 8800 5353/udp

# Virgil web panel / REST API
EXPOSE 8480

# AirPlay
EXPOSE 5000/tcp 5000/udp

# Snapcast
EXPOSE 1704/tcp 1705/tcp 1706/tcp

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl -fs http://127.0.0.1:8480/api/status >/dev/null || exit 1

# Entrypoint script
COPY docker-entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

# Start all services
CMD ["/app/entrypoint.sh"]
