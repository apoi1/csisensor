# Broker image with the project config baked in at build time.
# Rationale: a runtime bind mount of ./docker/mosquitto/mosquitto.conf
# requires WSL's distro-mount services when docker compose runs from
# Windows over the \\wsl.localhost share, and those are not always
# available (e.g. Windows 10 + WSL 3.x). Baking the config into the
# image keeps the whole broker workflow drivable from PowerShell.
# Config changes now require: docker compose up -d --build mosquitto
FROM eclipse-mosquitto:2
COPY mosquitto.conf /mosquitto/config/mosquitto.conf
