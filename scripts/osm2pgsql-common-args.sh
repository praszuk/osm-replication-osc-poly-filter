#!/bin/bash
set -e

# https://osm2pgsql.org/doc/manual.html
# shellcheck disable=SC2034
COMMON_OSM2PGSQL_ARGS=(
  --slim  # required for replication (increases database size and duplicates data)
  --extra-attributes  # includes metadata (userid, changesetid)
  --output=flex  #  provides custom database schema (tables/columns)
  --style=/schema.lua  # path to custom database schema
)