# Baking Python + the YT Music -> Lidarr sync engine into the lidarr image means
# no one has to `apk add` Python or copy files into a running container - they just
# install the plugin and paste their auth.
#
# Build:   docker build -f docker/Dockerfile -t lidarr-ytm:develop .
# Use:     replace your lidarr image with lidarr-ytm:develop (keep the same config + music mounts)
ARG LIDARR_TAG=develop
FROM ghcr.io/linuxserver/lidarr:${LIDARR_TAG}

COPY sync /app/sync
COPY docker/config.ini.dist /app/sync/config.ini

USER root
RUN apk add --no-cache python3 py3-pip \
 && python3 -m pip install --no-cache-dir --break-system-packages -r /app/sync/requirements.txt \
 && chown -R abc:abc /app/sync
USER abc