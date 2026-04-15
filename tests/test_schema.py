import tempfile

from tests.conftest import run_osm2pgsql


class TestOSM2PGSQLCustomLuaFlexSchema:
    def test_schema_untagged_nodes_skipped(self, db_conn):
        content = """
        <?xml version="1.0" encoding="UTF-8"?>
        <osm version="0.6" generator="test 1.0" >
            <node id="1" lat="0.0" lon="0.0" user="test_user" uid="1" version="1" changeset="1" timestamp="2025-01-01T00:00:00Z">
                <tag k="shop" v="convenience"/>
            </node>
            <node id="2" lat="1.0" lon="0.0" user="test_user" uid="1" version="1" changeset="1" timestamp="2025-01-01T00:00:00Z"/>
        </osm>
        """.strip()
        with tempfile.NamedTemporaryFile(mode='w+', suffix='.osm') as f:
            f.write(content)
            f.flush()

            run_osm2pgsql(db_conn.info.dbname, f.name, append=False)

        with db_conn.cursor() as cur:
            planet_osm_nodes_count = cur.execute('select count(*) from planet_osm_nodes').fetchone()
            nodes_count = cur.execute('select count(*) from nodes').fetchone()
            assert planet_osm_nodes_count[0] == (nodes_count[0] + 1) == 2

        append_content = """
        <?xml version="1.0" encoding="UTF-8"?>
        <osmChange version="0.6" generator="test 1.0">
            <modify>
                <node id="2" lat="5.0" lon="0.0" user="test_user" uid="1" version="2" changeset="2" timestamp="2025-01-02T00:00:00Z"/>
            </modify>
            <create>
                <node id="3" lat="1.0" lon="0.0" user="test_user" uid="1" version="1" changeset="2" timestamp="2025-01-02T00:00:00Z"/>
            </create>
        </osmChange>
        """.strip()
        with tempfile.NamedTemporaryFile(mode='w+', suffix='.osc') as f:
            f.write(append_content)
            f.flush()

            run_osm2pgsql(db_conn.info.dbname, f.name, append=True)

        with db_conn.cursor() as cur:
            planet_osm_nodes_count = cur.execute('select count(*) from planet_osm_nodes').fetchone()
            nodes_count = cur.execute('select count(*) from nodes').fetchone()
            assert planet_osm_nodes_count[0] == (nodes_count[0] + 2) == 3

    def test_schema_each_osm_object_type_has_geometry(self, db_conn):
        content = """
        <?xml version="1.0" encoding="UTF-8"?>
        <osm version="0.6" generator="test 1.0" >
            <node id="1" lat="-1.0" lon="-1.0" user="test_user" uid="1" version="1" changeset="1" timestamp="2025-01-01T00:00:00Z">
                <tag k="shop" v="convenience"/>
            </node>
            <node id="2" lat="0.0" lon="0.0" user="test_user" uid="1" version="1" changeset="1" timestamp="2025-01-01T00:00:00Z"/>
            <node id="3" lat="0.0" lon="2.0" user="test_user" uid="1" version="1" changeset="1" timestamp="2025-01-01T00:00:00Z"/>
            <node id="4" lat="1.0" lon="1.0" user="test_user" uid="1" version="1" changeset="1" timestamp="2025-01-01T00:00:00Z"/>
            <way id="1" user="test_user" uid="1" version="1" changeset="1" timestamp="2025-01-01T00:00:00Z">
                <nd ref="2"/>
                <nd ref="3"/>
                <nd ref="4"/>
                <nd ref="2"/>
                <tag k="building" v="house"/>
            </way>
            <relation id="1" user="test_user" uid="1" version="1" changeset="1" timestamp="2025-01-01T00:00:00Z">
                <member type="way" ref="1" role="outer"/>
                <tag k="type" v="multipolygon"/>
                <tag k="name" v="test"/>  
            </relation>
        </osm>
        """.strip()
        with tempfile.NamedTemporaryFile(mode='w+', suffix='.osm') as f:
            f.write(content)
            f.flush()

            run_osm2pgsql(db_conn.info.dbname, f.name, append=False)

        with db_conn.cursor() as cur:
            node_geom = cur.execute(
                'select ST_AsGeoJSON(geom)::json from nodes where node_id = 1'
            ).fetchone()[0]
            way_geom = cur.execute(
                'select ST_AsGeoJSON(geom)::json from ways where way_id = 1'
            ).fetchone()[0]
            relation_geom = cur.execute(
                'select ST_AsGeoJSON(geom)::json from relations where relation_id = 1'
            ).fetchone()[0]

        assert node_geom == {'type': 'Point', 'coordinates': [-1, -1]}
        assert way_geom == {'type': 'LineString', 'coordinates': [[0, 0], [2, 0], [1, 1], [0, 0]]}
        assert relation_geom == {
            'type': 'MultiPolygon',
            'coordinates': [[[[0, 0], [2, 0], [1, 1], [0, 0]]]],
        }
