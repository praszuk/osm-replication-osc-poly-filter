# OSM Replication OSC Poly Filter

This project simplifies creating and updating a PostGIS database for OSM data using [osm2pgsql](https://osm2pgsql.org/).

The target DB state:
- Designed for use with osm2pgsql
- Allows starting with any OSM PBF (e.g. Geofabrik extracts)
- Includes metadata (usernames, changesets)
- No history (no attic data)
- Minutely replication using `planet.osm.org`

## Requirements

You will need:
- Docker + docker compose
- An OSM account – to download the dump with metadata
- Enough storage for the selected region – the database size will be [much larger](https://osm2pgsql.org/doc/manual.html#sizing) than the downloaded .pbf file.

## How to use
The example is based on the Poland dump (February 2026), but I recommend trying this first with a smaller region before importing the entire country.

### Load pbf dump
1. Download project example files:
   - Clone [example project](https://github.com/praszuk/example-osm-replication-osc-poly-filter) – it's using already built [dockerhub image](https://hub.docker.com/r/praszuk/osm-replication-osc-poly-filter) (faster)
   - or clone this one – build will take up to few minutes
2. Prepare osm pbf file or download ready extract e.g. the latest Geofabrik region dump with metadata
   - Go to: https://download.geofabrik.de/europe/poland.html
   - Click on _Extracts with full metadata_
   - Log in via OSM account
   - Download `poland-latest-internal.osm.pbf` (2.3 GB) and `.poly` file
   - Move both files to the project directory: `data/`
3. Run containers:
   
   Copy or rename `example.env` to `.env` and change _POSTGRES_PASSWORD_.\
   Then run:
    ```bash
    docker compose up -d
    ```
   This will build containers and create an empty PostGIS database.
4. Init the osm2pgsql schema and load the dump
    
   Loading the Poland .pbf took about 1.5 hours on my machine and about 4 hours in a Proxmox container with 4 GB of memory and 1 CPUs. 
   The DB size is 46 GB (from a 2.3 GB .pbf file), but during the import, the db grew over 70 GB in the post-processing/indexing step.
    
    **Edit the last argument to match your downloaded filename!** 
   ```bash
    docker compose run --rm import bash -c './scripts/create.sh /data/poland-xxxx.osm.pbf'
    ```

### Replication
In general, this project tries to perform replication by checking if every object is in the polygon (poly), but
to keep it efficient and due to limitations of the osc diff structure, there may still be unwanted objects imported to the db.
For example:
- If a node is outside the poly, then moved inside, and then moved outside again, it will still be appended to the db.
- A way object might be appended even if it was never in the poly – this is possible because the program checks if any node of the way is in the poly or if the way already exists in the db. \
In one .osc file, we can have multiple versions of the same way due to different actions (created/modified/deleted), so they can contain different nodes. 
The problem is that .osc files don't contain specific node versions, only ids `<nd ref="5"/>`, so the program checks all nodes of the way in the osc/db, 
and if any node matches (even if it's no longer a member of the way), then the way will be appended.

These cases usually occur near borders or due to anomalies/vandalism. If it's important, you can always recreate the db from a dump periodically.

To understand how the filter works with different cases, you can check the [integration osc filter tests](tests/test_osc_poly_filter_integration.py).

---

To perform replication, run the command below. It will run endlessly.
Initially, it won't sleep between iterations to allow faster sync. After catching up the latest state, it will sleep between each iteration.

Replace `poland.poly` with the downloaded `.poly` filename.
```bash
 docker compose run --rm -it import bash -c './scripts/replicate.sh /data/poland.poly'
 ```

### Schema
If you want to change the schema and create your own tables, you can find examples in the [osm2pgsql repo](https://github.com/osm2pgsql-dev/osm2pgsql/blob/master/flex-config/README.md).

To modify the schema edit file `schemas/schema.lua`.

If you want to **remove all db data** to recreate it with the new schema, use:
```bash
docker compose down --volumes
```
and repeat section **Load pbf dump**.

### Explore
The database is running on localhost with the default port 5432. You can connect with your client/app or join via docker exec.
 ```bash
 docker compose exec -it db bash -c 'psql -d $POSTGRES_DB -U $POSTGRES_USER -p $POSTGRES_PORT'
 ```

**Meta cheatsheet:**
 ```sql
 -- show databases with sizes
 \l+

 -- list all tables (add + to show size) 
 \d 
 
 -- show columns/schema for table
 \d table_name
```

**Tag queries cheatsheet:**

```sql
-- nodes with highway=bus_stop tag
SELECT * FROM nodes WHERE tags @> '{"highway": "bus_stop"}' ORDER BY node_id DESC LIMIT 5;

-- nodes with highway=bus_stop and lit=yes
SELECT * FROM nodes WHERE tags @> '{"highway": "bus_stop", "lit": "yes"}' ORDER BY node_id DESC LIMIT 3;

-- nodes with highway=bus_stop without public_transport=platform
SELECT * FROM nodes WHERE tags @> '{"highway": "bus_stop"}' AND NOT tags @> '{"public_transport": "platform"}' ORDER BY node_id DESC LIMIT 3;

-- nodes with highway=bus_stop in 'powiat opolski' area based on teryt:terc tag
SELECT * FROM nodes n WHERE tags @> '{"highway": "bus_stop"}' AND ST_Contains((SELECT r.geom FROM relations r WHERE tags @> '{"teryt:terc": "1609"}' LIMIT 1), n.geom);

-- ways with highway=residential and their road names or none if they don't have
SELECT way_id, tags->'name' AS name FROM ways WHERE tags @> '{"highway": "residential"}' ORDER BY way_id DESC LIMIT 3;

-- nodes with created_by key
SELECT * FROM nodes WHERE tags ? 'created_by' ORDER BY node_id DESC LIMIT 3;
```
Note: Columns tags and members use jsonb type. You can find more in [postgres docs](https://www.postgresql.org/docs/current/functions-json.html#FUNCTIONS-JSON-PROCESSING).

### Read only user
If you want to create read-only database user (for example, to share access across multiple apps), run:
```bash
docker compose exec -it db bash -c "psql -d \$POSTGRES_DB -U \$POSTGRES_USER -p \$POSTGRES_PORT -c \"CREATE ROLE osm_ro WITH LOGIN PASSWORD 'osm_ro'; GRANT CONNECT ON DATABASE \$POSTGRES_DB TO osm_ro; GRANT USAGE ON SCHEMA public TO osm_ro; GRANT SELECT ON ALL TABLES IN SCHEMA public TO osm_ro; ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO osm_ro;\""
```
Login / Pass: `osm_ro`

## License
[MIT](LICENSE)