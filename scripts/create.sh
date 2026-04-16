#!/bin/bash
set -e

source ./scripts/osm2pgsql-common-args.sh
osm2pgsql --create "${COMMON_OSM2PGSQL_ARGS[@]}" -d $POSTGRES_DB -U $POSTGRES_USER -H $POSTGRES_HOST -P $POSTGRES_PORT $1