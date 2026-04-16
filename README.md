# Docker OSM Replication OSC Poly Filter

This project simplifies creating and updating a PostGIS database for OSM data using [osm2pgsql](https://osm2pgsql.org/).

The target DB state:
- Designed for use with osm2pgsql
- Allows starting with any OSM PBF (e.g. Geofabrik extracts)
- Includes metadata (usernames, changesets)
- No history (no attic data)
- Minutely replication using `planet.osm.org`

# Requirements

You will need:
- Docker + docker compose
- An OSM account – to download the dump with metadata
- Enough storage for the selected region – the database size will be [much larger](https://osm2pgsql.org/doc/manual.html#sizing) than the downloaded .pbf file.

# How to use
The example is based on the Poland dump (February 2026), but I recommend trying this first with a smaller region before importing the entire country.

## Load pbf dump
1. Download the project files
2. Download the latest region dump with metadata
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
    
    Loading the Poland .pbf took about 1.5 hours on my machine. The DB size is 46 GB (from a 2.3 GB .pbf file).
    
    **Edit the last argument to match your downloaded filename!** 
   ```bash
    docker compose run --rm import bash -c './scripts/create.sh /data/poland-xxxx.osm.pbf'
    ```
   For more details, see the [osm2pgsql manual](https://osm2pgsql.org/doc/manual.html).

## Replication
This runs until stopped or until the first critical error.

Replace `poland.poly` with the downloaded `.poly` filename.
```bash
 docker compose run --rm -it import bash -c './scripts/replicate.sh /data/poland.poly'
 ```

## Schema
If you want to change the schema and create your own tables, you can find examples in the [osm2pgsql repo](https://github.com/osm2pgsql-dev/osm2pgsql/blob/master/flex-config/README.md).

To modify the schema edit file `schema.lua`.
Then rebuild the container:
```bash
docker compose build
```

If you want to **remove all db data** to recreate it with the new schema, use:
```bash
docker compose down --volumes
```
and repeat section **Load pbf dump**.

## Explore
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

## Read only user
If you want to create read-only database user (for example, to share access across multiple apps), run:
```bash
docker compose exec -it db bash -c "psql -d \$POSTGRES_DB -U \$POSTGRES_USER -p \$POSTGRES_PORT -c \"CREATE ROLE osm_ro WITH LOGIN PASSWORD 'osm_ro'; GRANT CONNECT ON DATABASE \$POSTGRES_DB TO osm_ro; GRANT USAGE ON SCHEMA public TO osm_ro; GRANT SELECT ON ALL TABLES IN SCHEMA public TO osm_ro; ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO osm_ro;\""
```
Login / Pass: `osm_ro`

# License
[MIT](LICENSE)