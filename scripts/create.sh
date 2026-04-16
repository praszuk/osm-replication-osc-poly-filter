#!/bin/bash
set -e

source ./scripts/osm2pgsql-common-args.sh
osm2pgsql --slim --create --extra-attributes --output=flex --style=/schema.lua -d $POSTGRES_DB -U $POSTGRES_USER -H $POSTGRES_HOST -P $POSTGRES_PORT $1