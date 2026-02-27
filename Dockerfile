FROM debian:trixie-slim

RUN apt-get update && apt-get install -y osm2pgsql pyosmium osmium-tool
COPY schema.lua ./
