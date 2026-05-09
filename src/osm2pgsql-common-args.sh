#!/bin/bash
set -e

# https://osm2pgsql.org/doc/manual.html
# shellcheck disable=SC2034
COMMON_OSM2PGSQL_ARGS=(
  --slim  # required for replication (increases database size and duplicates data)
  --output=flex  #  provides custom database schema (tables/columns)
  --style=/schemas/schema.lua  # path to custom database schema
)

# includes metadata (columns: version, timestamp, changeset, uid, username)
if [[ ${OSM2PGSQL_USE_METADATA} == "true" ]]; then
    COMMON_OSM2PGSQL_ARGS+=(--extra-attributes)
fi
