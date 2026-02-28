FROM debian:trixie-slim

RUN apt-get update && apt-get install -y osm2pgsql pyosmium osmium-tool curl
COPY replicate.sh schema.lua ./
