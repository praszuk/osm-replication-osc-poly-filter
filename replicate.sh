#!/bin/bash
set -e

POLYFILE=$1
SCHEMAFILE=/schema.lua
STATEFILE=/sequence.state

latest_osm_obj_db_ts=''

log() {
  echo "$(date +'%Y-%m-%d %H:%M:%S') $1"
}

fetch_latest_osm_object_timestamp_from_db() {
  latest_osm_obj_db_ts=$(psql -A -t -d $POSTGRES_DB -U $POSTGRES_USER -h $POSTGRES_HOST -p $POSTGRES_PORT -c "
    SELECT to_char(max(created)::timestamp at time zone 'UTC', 'YYYY-MM-DD\"T\"HH24:MI:SS\"Z\"')
    FROM (
        (SELECT created FROM planet_osm_nodes ORDER BY id DESC LIMIT 1)
        UNION
        (SELECT created FROM planet_osm_ways ORDER BY id DESC LIMIT 1)
        UNION
        (SELECT created FROM planet_osm_rels ORDER BY id DESC LIMIT 1)
    );
  ")
  log "Latest OSM object timestamp from db: ${latest_osm_obj_db_ts}"
}

print_replication_state_id() {
  log "Current replication state id: $(cat $STATEFILE)"
}

# Init replication
fetch_latest_osm_object_timestamp_from_db
pyosmium-get-changes -D $latest_osm_obj_db_ts -f $STATEFILE -v

# Run replication
while true; do
    rm -f /tmp/changes.osc.gz /tmp/planet_changes.osc.gz

    # https://docs.osmcode.org/pyosmium/latest/user_manual/10-Replication-Tools/
    # Uses planet.osm.org minutely as default server
    set +e
    pyosmium-get-changes -f $STATEFILE -o /tmp/planet_changes.osc.gz -v
    status=$?
    set -e
    if [ $status -eq 0 ]; then
        log "Diff downloaded. Extracting .osc.gz using .poly file."
        osmium extract --polygon=$POLYFILE /tmp/planet_changes.osc.gz -o /tmp/changes.osc.gz
        log "Diff extracted. Appending data to the db."
        osm2pgsql --slim --append --extra-attributes --output=flex --style=$SCHEMAFILE -d $POSTGRES_DB -U $POSTGRES_USER -H $POSTGRES_HOST -P $POSTGRES_PORT /tmp/changes.osc.gz
        fetch_latest_osm_object_timestamp_from_db
        print_replication_state_id
    elif [ $status -eq 3 ]; then
        sleep 60
    else
        log "Fatal error, stopping updates."
        exit $status
    fi
done