#!/bin/bash
set -e

POLYFILE=$1
SCHEMAFILE=/schema.lua
STATEFILE=/data/sequence.state
SLEEP_TIME=60

latest_osm_obj_db_ts=''
server_state_id=''

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
}

refresh_server_state_id() {
  server_state_id="$(curl -s -L -X GET 'https://planet.osm.org/replication/minute/state.txt' | sed -n 's/^sequenceNumber=//p')";
}

# Initialize replication
fetch_latest_osm_object_timestamp_from_db
pyosmium-get-changes -D $latest_osm_obj_db_ts -f $STATEFILE -v
log "Latest OSM object timestamp from db: ${latest_osm_obj_db_ts}. Starting with state id: $(cat $STATEFILE)"

# Start replication loop
refresh_server_state_id
reached_remote_state_id=false
while true; do
    rm -f /tmp/changes.osc.gz /tmp/planet_changes.osc.gz

    # https://docs.osmcode.org/pyosmium/latest/user_manual/10-Replication-Tools/
    # Uses planet.osm.org minutely as default server
    set +e

    cp $STATEFILE ${STATEFILE}.tmp

    log "Downloading changes from state id: $(cat $STATEFILE)"
    pyosmium-get-changes -f ${STATEFILE}.tmp -o /tmp/planet_changes.osc.gz -v
    status=$?
    set -e
    if [ $status -eq 0 ]; then
        log "Diff downloaded. Extracting .osc.gz using .poly file."
        osmium extract --polygon=$POLYFILE /tmp/planet_changes.osc.gz -o /tmp/changes.osc.gz
        log "Diff extracted. Appending data to the db."
        osm2pgsql --slim --append --extra-attributes --output=flex --style=$SCHEMAFILE -d $POSTGRES_DB -U $POSTGRES_USER -H $POSTGRES_HOST -P $POSTGRES_PORT /tmp/changes.osc.gz

        old_state_id=$(cat $STATEFILE)
        new_state_id="$(cat $STATEFILE.tmp)"
        mv -u $STATEFILE.tmp $STATEFILE
        log "Diff applied. Updated state id: ${old_state_id} -> ${new_state_id}"

        # During initialization, we skip 'sleep' to synchronize with the replication server as fast as possible.
        # Once we catch up to the remote state, we compare the local state with the remote state again.
        # If they are equal or nearly equal, we start sleeping between iterations to avoid sending unnecessary requests.
        if [ "$reached_remote_state_id" = true ]; then
          sleep $SLEEP_TIME
          continue
        fi

        if (( "${server_state_id}" - "${new_state_id}" < 2 )); then
          # Refresh again to double check the remote state.
          # This handles very old dumps that may takes days to fully synchronize.
          refresh_server_state_id

          if (( "${server_state_id}" - "${new_state_id}" < 2 )); then
            log "Reached server state head ${server_state_id}. Sleeping after each apply from now on."
            reached_remote_state_id=true
            sleep $SLEEP_TIME
            continue
          fi
        fi
    elif [ $status -eq 3 ]; then
        sleep $SLEEP_TIME
    else
        log "Fatal error, stopping updates."
        exit $status
    fi
done