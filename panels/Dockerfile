# Home Deck in one container, as an alternative to install.sh + systemd.
# The server is pure standard library, so there is nothing to build and no venv:
# copy the tree, run it. What the image does not hold is the house - settings and
# state are volumes, so pulling a new image never touches them.
FROM python:3.12-slim

# iproute2: presence reads the ARP table ("ip neigh") to see which phones are home.
# curl: the health check below. tzdata: [general] timezone in the settings.
RUN apt-get update \
 && apt-get install -y --no-install-recommends iproute2 curl tzdata \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /opt/panel-wrapper
COPY server/server.py ./server.py
COPY server/homedeck ./homedeck
COPY server/www ./www
COPY server/homedeck.toml /opt/homedeck-template.toml
COPY onboard /opt/homedeck-onboard
COPY docker/entrypoint.sh docker/homedeck-apply /usr/local/sbin/

ARG VERSION=docker
RUN printf '%s\n' "$VERSION" > /opt/panel-wrapper/VERSION \
 && chmod +x /usr/local/sbin/entrypoint.sh /usr/local/sbin/homedeck-apply \
 && find /opt/panel-wrapper /opt/homedeck-onboard -name __pycache__ -prune -exec rm -rf {} +

# The code is in the image and read-only; only these two move.
# The settings live apart from the code here, which the systemd install does not
# do: there /opt/panel-wrapper holds both, so the wizard finds the homedeck
# package through ONBOARD_ROOT. With them split it needs the code named.
ENV PYTHONPATH=/opt/panel-wrapper \
    HOMEDECK_ROOT=/opt/panel-wrapper \
    HOMEDECK_CONFIG=/data/homedeck.toml \
    STATE_DIRECTORY=/state \
    HOMEDECK_PORT=80 \
    ONBOARD_ROOT=/data \
    ONBOARD_STATE=/state \
    ONBOARD_PORT=8089 \
    ONBOARD_CODE_FILE=/state/onboard.code \
    ONBOARD_APPLY=/usr/local/sbin/homedeck-apply \
    ONBOARD_STOP="touch /state/.onboard-done"
VOLUME ["/data", "/state"]
EXPOSE 80 8089

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s \
  CMD curl -fs -m 3 -o /dev/null "http://127.0.0.1:${HOMEDECK_PORT}/api/health" || exit 1

ENTRYPOINT ["/usr/local/sbin/entrypoint.sh"]
