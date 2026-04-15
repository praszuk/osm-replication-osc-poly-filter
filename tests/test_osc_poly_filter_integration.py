import tempfile
from pathlib import Path

from lxml import etree
import pytest

from tests.conftest import run_osm2pgsql, run_osc_poly_filter


class BaseOscPolyFilter:
    """
    About all tests
    Each test assume all possible properties doesn't fit to make a match.
    It means if we have a node, it's not in area, db or osc file.
    If we have a way, it doesn't have a node (as above) etc.

    There also tests which checks previous actions in osc file.
    Filtering is processed in batches
    One .osc file can contain multiple changesets which means it can contain full
    lifecycle of OSM object – it can be created, modified and deleted in one file.
    If at least one version of object met the condition then it will be treateda as matched.
    All create/modife/delete action of this object will be included in the output file.
    """

    @pytest.fixture
    def poly05_filename(self):
        # fmt: off
        content = (
            'poly\n'
            'area1\n'
            '0 0\n'
            '0 5\n'
            '5 5\n'
            '5 0\n'
            '0 0\n'
            'END\n'
        )
        # fmt: on
        with tempfile.NamedTemporaryFile(mode='w+', suffix='.poly') as f:
            f.write(content)
            f.flush()

            yield f.name

    @staticmethod
    def perform(
        dbname: str, osm_db_elements_xml: str, poly05_filename: str, osc_actions_xml: str
    ) -> etree._Element:
        with tempfile.NamedTemporaryFile(mode='w+', suffix='.osm') as f:
            osm_db_content = f"""
            <?xml version="1.0" encoding="UTF-8"?>
            <osm version="0.6" generator="test 1.0" >
                {osm_db_elements_xml}
            </osm>
            """.strip()
            f.write(osm_db_content)
            f.flush()

            run_osm2pgsql(dbname, f.name, append=False)

        with tempfile.TemporaryDirectory() as tmpdir:
            with tempfile.NamedTemporaryFile(mode='w+', suffix='.osc') as input_file:
                osc_content = f"""
                <?xml version="1.0" encoding="UTF-8"?>
                <osmChange version="0.6" generator="test 1.0">
                    {osc_actions_xml}
                </osmChange>
                """.strip()
                input_file.write(osc_content)
                input_file.flush()

                output_file = Path(tmpdir) / 'filtered.osc'

                run_osc_poly_filter(
                    dbname, poly05_filename, input_file.name, str(output_file.resolve())
                )

                return etree.fromstring(output_file.read_bytes())


class TestOscPolyFilterNodeCreate(BaseOscPolyFilter):
    def test_in_area(self, db_conn, poly05_filename):
        osm_elements = """
        <node id="1" lat="2.0" lon="2.0" user="test_user" uid="1" version="1" changeset="1" timestamp="2025-01-01T00:00:00Z">
            <tag k="shop" v="convenience"/>
        </node>
        """.strip()
        osc_actions = """    
        <create>
            <node id="2" lat="1.0" lon="0.0" user="test_user" uid="1" version="1" changeset="2" timestamp="2025-01-02T00:00:00Z">
                <tag k="amenity" v="bench"/>
            </node>
        </create>
        """.strip()

        elem = self.perform(db_conn.info.dbname, osm_elements, poly05_filename, osc_actions)
        assert elem.xpath('.//node[@id="2"]')

    def test_skip_not_in_area(self, db_conn, poly05_filename):
        osm_elements = """
        <node id="1" lat="2.0" lon="2.0" user="test_user" uid="1" version="1" changeset="1" timestamp="2025-01-01T00:00:00Z">
            <tag k="shop" v="convenience"/>
        </node>
        """.strip()
        osc_actions = """    
        <create>
            <node id="2" lat="6.0" lon="0.0" user="test_user" uid="1" version="1" changeset="2" timestamp="2025-01-02T00:00:00Z">
                <tag k="amenity" v="bench"/>
            </node>
        </create>
        """.strip()

        elem = self.perform(db_conn.info.dbname, osm_elements, poly05_filename, osc_actions)
        assert not elem.xpath('.//node[@id="2"]')


class TestOscPolyFilterNodeModify(BaseOscPolyFilter):
    def test_in_area(self, db_conn, poly05_filename):
        """
        It can happen when the node has been moved into poly.
        We don't need to have it in db.
        """
        osm_elements = """
        <node id="1" lat="2.0" lon="2.0" user="test_user" uid="1" version="1" changeset="1" timestamp="2025-01-01T00:00:00Z">
            <tag k="shop" v="convenience"/>
        </node>
        """.strip()
        osc_actions = """    
        <modify>
            <node id="1" lat="1.0" lon="0.0" user="test_user" uid="1" version="2" changeset="2" timestamp="2025-01-02T00:00:00Z">
                <tag k="amenity" v="bench"/>
            </node>
            <node id="2" lat="5.0" lon="5.0" user="test_user" uid="1" version="1" changeset="2" timestamp="2025-01-02T00:00:00Z">
                <tag k="natural" v="tree"/>
            </node>
        </modify>
        """.strip()

        elem = self.perform(db_conn.info.dbname, osm_elements, poly05_filename, osc_actions)
        assert elem.xpath('.//node[@id="1"]')
        assert elem.xpath('.//node[@id="2"]')

    def test_in_db(self, db_conn, poly05_filename):
        """
        It will update nodes also outside the poly – if way in the osc is crossing the
        border, then all nodes are being stored in db to keep the way completed,
        It's not required to check if node is in the area
        """
        osm_elements = """
        <node id="1" lat="6.0" lon="6.0" user="test_user" uid="1" version="1" changeset="1" timestamp="2025-01-01T00:00:00Z">
            <tag k="shop" v="convenience"/>
        </node>
        """.strip()
        osc_actions = """    
        <modify>
            <node id="1" lat="7.0" lon="7.0" user="test_user" uid="1" version="2" changeset="2" timestamp="2025-01-02T00:00:00Z">
                <tag k="amenity" v="bench"/>
            </node>
        </modify>
        """.strip()

        elem = self.perform(db_conn.info.dbname, osm_elements, poly05_filename, osc_actions)
        assert elem.xpath('.//node[@id="1"]')

    def test_skip_not_in_area_and_not_in_db(self, db_conn, poly05_filename):
        osm_elements = """
        <node id="1" lat="6.0" lon="6.0" user="test_user" uid="1" version="1" changeset="1" timestamp="2025-01-01T00:00:00Z">
            <tag k="shop" v="convenience"/>
        </node>
        """.strip()
        osc_actions = """    
        <modify>
            <node id="2" lat="7.0" lon="7.0" user="test_user" uid="1" version="2" changeset="2" timestamp="2025-01-02T00:00:00Z">
                <tag k="amenity" v="bench"/>
            </node>
        </modify>
        """.strip()

        elem = self.perform(db_conn.info.dbname, osm_elements, poly05_filename, osc_actions)
        assert not elem.xpath('.//node[@id="2"]')

    def test_osc_any_action_in_osc_in_area(self, db_conn, poly05_filename):
        """
        It might happen that node will be traveling beteen border even in one .osc file
        If we find at last one version which should qualify to the include to output diff,
        then it should contain the all the actions.
        """
        osm_elements = """
        <node id="1" lat="6.0" lon="6.0" user="test_user" uid="1" version="1" changeset="1" timestamp="2025-01-01T00:00:00Z">
            <tag k="shop" v="convenience"/>
        </node>
        """.strip()
        osc_actions = """
        <create>
            <node id="2" lat="7.0" lon="7.0" user="test_user" uid="1" version="1" changeset="2" timestamp="2025-01-02T00:00:00Z">
                <tag k="amenity" v="bench"/>
            </node>
        </create>
        <modify>
            <node id="2" lat="3.0" lon="3.0" user="test_user" uid="1" version="2" changeset="3" timestamp="2025-01-02T00:00:00Z">
                <tag k="amenity" v="bench"/>
            </node>
        </modify>
        <delete>
            <node id="2" user="test_user" uid="1" version="3" changeset="4" timestamp="2025-01-02T00:00:00Z"/>
        </delete>
        <modify>
            <node id="2" lat="8.0" lon="8.0" user="test_user" uid="1" version="4" changeset="5" timestamp="2025-01-02T00:00:00Z">
                <tag k="natural" v="tree"/>
            </node>
        </modify>
        """.strip()

        elem = self.perform(db_conn.info.dbname, osm_elements, poly05_filename, osc_actions)
        assert elem.xpath('.//node[@id="2"]/@version') == ['1', '2', '3', '4']

    def test_osc_skip_all_actions_in_osc_not_in_area(self, db_conn, poly05_filename):
        osm_elements = """
        <node id="1" lat="6.0" lon="6.0" user="test_user" uid="1" version="1" changeset="1" timestamp="2025-01-01T00:00:00Z">
            <tag k="shop" v="convenience"/>
        </node>
        """.strip()
        osc_actions = """
        <create>
            <node id="2" lat="7.0" lon="7.0" user="test_user" uid="1" version="1" changeset="2" timestamp="2025-01-02T00:00:00Z">
                <tag k="amenity" v="bench"/>
            </node>
        </create>
        <modify>
            <node id="2" lat="10.0" lon="10.0" user="test_user" uid="1" version="2" changeset="3" timestamp="2025-01-02T00:00:00Z">
                <tag k="amenity" v="bench"/>
            </node>
        </modify>
        <delete>
            <node id="2" user="test_user" uid="1" version="3" changeset="4" timestamp="2025-01-02T00:00:00Z"/>
        </delete>
        <modify>
            <node id="2" lat="8.0" lon="8.0" user="test_user" uid="1" version="4" changeset="5" timestamp="2025-01-02T00:00:00Z">
                <tag k="natural" v="tree"/>
            </node>
        </modify>
        """.strip()

        elem = self.perform(db_conn.info.dbname, osm_elements, poly05_filename, osc_actions)
        assert elem.xpath('.//node[@id="2"]/@version') == []


class TestOscPolyFilterNodeDelete(BaseOscPolyFilter):
    def test_in_db(self, db_conn, poly05_filename):
        osm_elements = """
        <node id="1" lat="6.0" lon="6.0" user="test_user" uid="1" version="1" changeset="1" timestamp="2025-01-01T00:00:00Z">
            <tag k="shop" v="convenience"/>
        </node>
        """.strip()
        osc_actions = """    
        <delete>
            <node id="1" user="test_user" uid="1" version="2" changeset="2" timestamp="2025-01-02T00:00:00Z"/>
        </delete>
        """.strip()

        elem = self.perform(db_conn.info.dbname, osm_elements, poly05_filename, osc_actions)
        assert elem.xpath('.//node[@id="1"]')

    def test_skip_not_in_db(self, db_conn, poly05_filename):
        osm_elements = """
        <node id="1" lat="6.0" lon="6.0" user="test_user" uid="1" version="1" changeset="1" timestamp="2025-01-01T00:00:00Z">
            <tag k="shop" v="convenience"/>
        </node>
        """.strip()
        osc_actions = """    
        <delete>
            <node id="2" user="test_user" uid="1" version="2" changeset="2" timestamp="2025-01-02T00:00:00Z"/>
        </delete>
        """.strip()

        elem = self.perform(db_conn.info.dbname, osm_elements, poly05_filename, osc_actions)
        assert not elem.xpath('.//node[@id="1"]')

    def test_osc_any_action_in_osc_in_area(self, db_conn, poly05_filename):
        """
        It might happen that node doesn't exist yet, but .osc might contain it (create/modify)
        We should keep all related actions to that object (e.g. historical reason) and delete it also
        if it shoule be deleted at the end, because previous actions can create it.
        """
        osm_elements = """
        <node id="1" lat="6.0" lon="6.0" user="test_user" uid="1" version="1" changeset="1" timestamp="2025-01-01T00:00:00Z">
            <tag k="shop" v="convenience"/>
        </node>
        """.strip()
        osc_actions = """
        <create>
            <node id="2" lat="7.0" lon="7.0" user="test_user" uid="1" version="1" changeset="2" timestamp="2025-01-02T00:00:00Z">
                <tag k="amenity" v="bench"/>
            </node>
        </create>
        <modify>
            <node id="2" lat="3.0" lon="3.0" user="test_user" uid="1" version="2" changeset="3" timestamp="2025-01-02T00:00:00Z">
                <tag k="amenity" v="bench"/>
            </node>
        </modify>
        <delete>
            <node id="2" user="test_user" uid="1" version="3" changeset="4" timestamp="2025-01-02T00:00:00Z"/>
        </delete>
        """.strip()

        elem = self.perform(db_conn.info.dbname, osm_elements, poly05_filename, osc_actions)
        assert elem.xpath('.//node[@id="2"]/@version') == ['1', '2', '3']

    def test_osc_skip_all_actions_in_osc_not_in_area(self, db_conn, poly05_filename):
        osm_elements = """
        <node id="1" lat="6.0" lon="6.0" user="test_user" uid="1" version="1" changeset="1" timestamp="2025-01-01T00:00:00Z">
            <tag k="shop" v="convenience"/>
        </node>
        """.strip()
        osc_actions = """
        <create>
            <node id="2" lat="7.0" lon="7.0" user="test_user" uid="1" version="1" changeset="2" timestamp="2025-01-02T00:00:00Z">
                <tag k="amenity" v="bench"/>
            </node>
        </create>
        <modify>
            <node id="2" lat="8.0" lon="8.0" user="test_user" uid="1" version="2" changeset="3" timestamp="2025-01-02T00:00:00Z">
                <tag k="amenity" v="bench"/>
            </node>
        </modify>
        <delete>
            <node id="2" user="test_user" uid="1" version="3" changeset="4" timestamp="2025-01-02T00:00:00Z"/>
        </delete>
        """.strip()

        elem = self.perform(db_conn.info.dbname, osm_elements, poly05_filename, osc_actions)
        assert elem.xpath('.//node[@id="2"]/@version') == []


class TestOscPolyFilterWayCreate(BaseOscPolyFilter):
    def test_db_any_node_in_db_and_in_area(self, db_conn, poly05_filename):
        osm_elements = """
        <node id="1" lat="-1.0" lon="-1.0" user="test_user" uid="1" version="1" changeset="1" timestamp="2025-01-01T00:00:00Z">
            <tag k="highway" v="traffic_signals"/>
        </node>
        <node id="2" lat="3.0" lon="3.0" user="test_user" uid="1" version="1" changeset="1" timestamp="2025-01-01T00:00:00Z">
            <tag k="highway" v="crossing"/>
        </node>
        <node id="3" lat="10.0" lon="10.0" user="test_user" uid="1" version="1" changeset="1" timestamp="2025-01-01T00:00:00Z">
            <tag k="noexit" v="yes"/>
        </node>
        """.strip()
        osc_actions = """
        <create>
            <way id="1" user="test_user" uid="1" version="1" changeset="2" timestamp="2025-01-02T00:00:00Z">
                <nd ref="1"/>
                <nd ref="2"/>
                <nd ref="3"/>
                <tag k="highway" v="residential"/>
            </way>
        </create>
        """.strip()

        elem = self.perform(db_conn.info.dbname, osm_elements, poly05_filename, osc_actions)

        assert elem.xpath('.//way[@id="1"]')

    def test_db_skip_nodes_in_db_but_not_in_area(self, db_conn, poly05_filename):
        osm_elements = """
        <node id="1" lat="-1.0" lon="-1.0" user="test_user" uid="1" version="1" changeset="1" timestamp="2025-01-01T00:00:00Z">
            <tag k="highway" v="traffic_signals"/>
        </node>
        <node id="2" lat="7.0" lon="7.0" user="test_user" uid="1" version="1" changeset="1" timestamp="2025-01-01T00:00:00Z">
            <tag k="highway" v="crossing"/>
        </node>
        <node id="3" lat="10.0" lon="10.0" user="test_user" uid="1" version="1" changeset="1" timestamp="2025-01-01T00:00:00Z">
            <tag k="noexit" v="yes"/>
        </node>
        """.strip()
        osc_actions = """
        <create>
            <way id="1" user="test_user" uid="1" version="1" changeset="2" timestamp="2025-01-02T00:00:00Z">
                <nd ref="1"/>
                <nd ref="2"/>
                <nd ref="3"/>
                <tag k="highway" v="residential"/>
            </way>
        </create>
        """.strip()

        elem = self.perform(db_conn.info.dbname, osm_elements, poly05_filename, osc_actions)
        assert not elem.xpath('.//way[@id="1"]')

    def test_db_skip_nodes_not_in_db(self, db_conn, poly05_filename):
        osm_elements = """
        <node id="1" lat="3.0" lon="3.0" user="test_user" uid="1" version="1" changeset="1" timestamp="2025-01-01T00:00:00Z">
            <tag k="highway" v="traffic_signals"/>
        </node>
        """.strip()
        osc_actions = """
        <create>
            <way id="1" user="test_user" uid="1" version="1" changeset="2" timestamp="2025-01-02T00:00:00Z">
                <nd ref="2"/>
                <nd ref="3"/>
                <nd ref="4"/>
                <tag k="highway" v="residential"/>
            </way>
        </create>
        """.strip()

        elem = self.perform(db_conn.info.dbname, osm_elements, poly05_filename, osc_actions)
        assert not elem.xpath('.//way[@id="1"]')

    def test_osc_node_in_area(self, db_conn, poly05_filename):
        """
        It might happen that node doesn't exist yet in area, but .osc might contain it (create/modify)
        """
        osm_elements = """
        <node id="1" lat="3.0" lon="3.0" user="test_user" uid="1" version="1" changeset="1" timestamp="2025-01-01T00:00:00Z">
            <tag k="highway" v="traffic_signals"/>
        </node>
        """.strip()
        osc_actions = """
        <create>
            <node id="3" lat="7.0" lon="3.0" user="test_user" uid="1" version="1" changeset="2" timestamp="2025-01-01T00:00:00Z">
                <tag k="highway" v="traffic_signals"/>
            </node>
        </create>
        <modify>
            <node id="3" lat="4.0" lon="3.0" user="test_user" uid="1" version="2" changeset="3" timestamp="2025-01-01T00:00:00Z">
                <tag k="highway" v="traffic_signals"/>
            </node>
        </modify>
        <modify>
            <node id="3" lat="7.0" lon="3.0" user="test_user" uid="1" version="3" changeset="4" timestamp="2025-01-01T00:00:00Z">
                <tag k="highway" v="traffic_signals"/>
            </node>
        </modify>
        <create>
            <way id="1" user="test_user" uid="1" version="1" changeset="2" timestamp="2025-01-02T00:00:00Z">
                <nd ref="2"/>
                <nd ref="3"/>
                <nd ref="4"/>
                <tag k="highway" v="residential"/>
            </way>
        </create>
        """.strip()

        elem = self.perform(db_conn.info.dbname, osm_elements, poly05_filename, osc_actions)
        assert elem.xpath('.//way[@id="1"]')

    def test_osc_skip_nodes_not_in_area(self, db_conn, poly05_filename):
        osm_elements = """
        <node id="1" lat="3.0" lon="3.0" user="test_user" uid="1" version="1" changeset="1" timestamp="2025-01-01T00:00:00Z">
            <tag k="highway" v="traffic_signals"/>
        </node>
        """.strip()
        osc_actions = """
        <create>
            <node id="3" lat="7.0" lon="3.0" user="test_user" uid="1" version="1" changeset="2" timestamp="2025-01-01T00:00:00Z">
                <tag k="highway" v="traffic_signals"/>
            </node>
        </create>
        <modify>
            <node id="3" lat="7.0" lon="4.0" user="test_user" uid="1" version="2" changeset="3" timestamp="2025-01-01T00:00:00Z">
                <tag k="highway" v="traffic_signals"/>
            </node>
        </modify>
        <modify>
            <node id="3" lat="7.0" lon="3.0" user="test_user" uid="1" version="3" changeset="4" timestamp="2025-01-01T00:00:00Z">
                <tag k="highway" v="traffic_signals"/>
            </node>
        </modify>
        <create>
            <way id="1" user="test_user" uid="1" version="1" changeset="2" timestamp="2025-01-02T00:00:00Z">
                <nd ref="2"/>
                <nd ref="3"/>
                <nd ref="4"/>
                <tag k="highway" v="residential"/>
            </way>
        </create>
        """.strip()

        elem = self.perform(db_conn.info.dbname, osm_elements, poly05_filename, osc_actions)
        assert not elem.xpath('.//way[@id="1"]')


class TestOscPolyFilterWayModify(BaseOscPolyFilter):
    def test_db_any_node_in_db_and_in_area(self, db_conn, poly05_filename):
        osm_elements = """
        <node id="1" lat="-1.0" lon="-1.0" user="test_user" uid="1" version="1" changeset="1" timestamp="2025-01-01T00:00:00Z">
            <tag k="highway" v="traffic_signals"/>
        </node>
        <node id="2" lat="3.0" lon="3.0" user="test_user" uid="1" version="1" changeset="1" timestamp="2025-01-01T00:00:00Z">
            <tag k="highway" v="crossing"/>
        </node>
        <node id="3" lat="10.0" lon="10.0" user="test_user" uid="1" version="1" changeset="1" timestamp="2025-01-01T00:00:00Z">
            <tag k="noexit" v="yes"/>
        </node>
        """.strip()
        osc_actions = """
        <modify>
            <way id="1" user="test_user" uid="1" version="2" changeset="2" timestamp="2025-01-02T00:00:00Z">
                <nd ref="1"/>
                <nd ref="2"/>
                <nd ref="3"/>
                <tag k="highway" v="residential"/>
            </way>
        </modify>
        """.strip()

        elem = self.perform(db_conn.info.dbname, osm_elements, poly05_filename, osc_actions)
        assert elem.xpath('.//way[@id="1"]')

    def test_db_skip_nodes_in_db_but_not_in_area(self, db_conn, poly05_filename):
        osm_elements = """
        <node id="1" lat="-1.0" lon="-1.0" user="test_user" uid="1" version="1" changeset="1" timestamp="2025-01-01T00:00:00Z">
            <tag k="highway" v="traffic_signals"/>
        </node>
        <node id="2" lat="10.0" lon="10.0" user="test_user" uid="1" version="1" changeset="1" timestamp="2025-01-01T00:00:00Z">
            <tag k="noexit" v="yes"/>
        </node>
        """.strip()
        osc_actions = """
        <modify>
            <way id="1" user="test_user" uid="1" version="2" changeset="2" timestamp="2025-01-02T00:00:00Z">
                <nd ref="1"/>
                <nd ref="2"/>
                <tag k="highway" v="service"/>
            </way>
        </modify>
        """.strip()

        elem = self.perform(db_conn.info.dbname, osm_elements, poly05_filename, osc_actions)
        assert not elem.xpath('.//way[@id="1"]')

    def test_db_skip_nodes_and_way_not_in_db(self, db_conn, poly05_filename):
        osm_elements = """
        <node id="1" lat="3.0" lon="3.0" user="test_user" uid="1" version="1" changeset="1" timestamp="2025-01-01T00:00:00Z">
            <tag k="highway" v="traffic_signals"/>
        </node>
        """.strip()
        osc_actions = """
        <modify>
            <way id="1" user="test_user" uid="1" version="2" changeset="2" timestamp="2025-01-02T00:00:00Z">
                <nd ref="2"/>
                <nd ref="3"/>
                <tag k="highway" v="service"/>
            </way>
        </modify>
        """.strip()

        elem = self.perform(db_conn.info.dbname, osm_elements, poly05_filename, osc_actions)
        assert not elem.xpath('.//way[@id="1"]')

    def test_db_way_in_db(self, db_conn, poly05_filename):
        osm_elements = """
        <node id="1" lat="3.0" lon="3.0" user="test_user" uid="1" version="1" changeset="1" timestamp="2025-01-01T00:00:00Z">
            <tag k="highway" v="traffic_signals"/>
        </node>
        <way id="1" user="test_user" uid="1" version="1" changeset="1" timestamp="2025-01-02T00:00:00Z">
            <nd ref="2"/>
            <nd ref="3"/>
        </way>
        """.strip()
        osc_actions = """
        <modify>
            <way id="1" user="test_user" uid="1" version="2" changeset="2" timestamp="2025-01-02T00:00:00Z">
                <nd ref="2"/>
                <nd ref="3"/>
                <nd ref="4"/>
                <tag k="highway" v="service"/>
            </way>
        </modify>
        """.strip()

        elem = self.perform(db_conn.info.dbname, osm_elements, poly05_filename, osc_actions)
        assert elem.xpath('.//way[@id="1"]')

    def test_osc_node_in_area(self, db_conn, poly05_filename):
        """
        It might happen that node doesn't exist yet in area, but .osc might contain it (create/modify)
        """
        osm_elements = """
        <node id="1" lat="3.0" lon="3.0" user="test_user" uid="1" version="1" changeset="1" timestamp="2025-01-01T00:00:00Z">
            <tag k="highway" v="traffic_signals"/>
        </node>
        """.strip()
        osc_actions = """
        <create>
            <node id="3" lat="4.0" lon="4.0" user="test_user" uid="1" version="1" changeset="2" timestamp="2025-01-02T00:00:00Z">
                <tag k="highway" v="traffic_signals"/>
            </node>
        </create>
        <modify>
            <way id="1" user="test_user" uid="1" version="2" changeset="2" timestamp="2025-01-02T00:00:00Z">
                <nd ref="2"/>
                <nd ref="3"/>
                <nd ref="4"/>
                <tag k="highway" v="service"/>
            </way>
        </modify>
        """.strip()

        elem = self.perform(db_conn.info.dbname, osm_elements, poly05_filename, osc_actions)
        assert elem.xpath('.//way[@id="1"]')

    def test_osc_skip_nodes_not_in_area(self, db_conn, poly05_filename):
        osm_elements = """
        <node id="1" lat="3.0" lon="3.0" user="test_user" uid="1" version="1" changeset="1" timestamp="2025-01-01T00:00:00Z">
            <tag k="highway" v="traffic_signals"/>
        </node>
        """.strip()
        osc_actions = """
        <create>
            <node id="3" lat="7.0" lon="7.0" user="test_user" uid="1" version="1" changeset="2" timestamp="2025-01-02T00:00:00Z">
                <tag k="highway" v="traffic_signals"/>
            </node>
        </create>
        <modify>
            <way id="1" user="test_user" uid="1" version="2" changeset="2" timestamp="2025-01-02T00:00:00Z">
                <nd ref="2"/>
                <nd ref="3"/>
                <nd ref="4"/>
                <tag k="highway" v="service"/>
            </way>
        </modify>
        """.strip()

        elem = self.perform(db_conn.info.dbname, osm_elements, poly05_filename, osc_actions)
        assert not elem.xpath('.//way[@id="1"]')

    def test_osc_any_action_in_osc_other_way_included(self, db_conn, poly05_filename):
        """
        It might happen that node/way doesn't exist yet in area, but .osc might contain it (create/modify)
        """
        osm_elements = """
        <node id="1" lat="3.0" lon="3.0" user="test_user" uid="1" version="1" changeset="1" timestamp="2025-01-01T00:00:00Z">
            <tag k="highway" v="traffic_signals"/>
        </node>
        """.strip()
        osc_actions = """
        <create>
            <way id="1" user="test_user" uid="1" version="1" changeset="1" timestamp="2025-01-02T00:00:00Z">
                <nd ref="2"/>
                <nd ref="3"/>
                <tag k="highway" v="service"/>
            </way>
        </create>
        <modify>
            <way id="1" user="test_user" uid="1" version="2" changeset="2" timestamp="2025-01-03T00:00:00Z">
                <nd ref="2"/>
                <nd ref="1"/>
                <nd ref="4"/>
                <tag k="highway" v="service"/>
            </way>
        </modify>
        <modify>
            <way id="1" user="test_user" uid="1" version="3" changeset="3" timestamp="2025-01-04T00:00:00Z">
                <nd ref="2"/>
                <nd ref="3"/>
                <nd ref="4"/>
                <tag k="highway" v="service"/>
            </way>
        </modify>
        """.strip()

        elem = self.perform(db_conn.info.dbname, osm_elements, poly05_filename, osc_actions)
        assert elem.xpath('.//way[@id="1"]')

    def test_osc_skip_all_actions_in_osc_way_not_included(self, db_conn, poly05_filename):
        osm_elements = """
        <node id="1" lat="3.0" lon="3.0" user="test_user" uid="1" version="1" changeset="1" timestamp="2025-01-01T00:00:00Z">
            <tag k="highway" v="traffic_signals"/>
        </node>
        """.strip()
        osc_actions = """
        <create>
            <way id="1" user="test_user" uid="1" version="1" changeset="1" timestamp="2025-01-02T00:00:00Z">
                <nd ref="2"/>
                <nd ref="3"/>
                <tag k="highway" v="service"/>
            </way>
        </create>
        <modify>
            <way id="1" user="test_user" uid="1" version="2" changeset="2" timestamp="2025-01-03T00:00:00Z">
                <nd ref="2"/>
                <nd ref="4"/>
                <tag k="highway" v="service"/>
            </way>
        </modify>
        <modify>
            <way id="1" user="test_user" uid="1" version="3" changeset="3" timestamp="2025-01-04T00:00:00Z">
                <nd ref="2"/>
                <nd ref="3"/>
                <nd ref="4"/>
                <tag k="highway" v="service"/>
            </way>
        </modify>
        """.strip()

        elem = self.perform(db_conn.info.dbname, osm_elements, poly05_filename, osc_actions)
        assert not elem.xpath('.//way[@id="1"]')


class TestOscPolyFilterWayDelete(BaseOscPolyFilter):
    def test_db_way_in_db(self, db_conn, poly05_filename):
        osm_elements = """
        <way id="1" user="test_user" uid="1" version="1" changeset="1" timestamp="2025-01-02T00:00:00Z">
            <nd ref="2"/>
            <nd ref="3"/>
        </way>
        """.strip()
        osc_actions = """
        <delete>
            <way id="1" user="test_user" uid="1" version="2" changeset="2" timestamp="2025-01-02T00:00:00Z" />
        </delete>
        """.strip()

        elem = self.perform(db_conn.info.dbname, osm_elements, poly05_filename, osc_actions)
        assert elem.xpath('.//way[@id="1"]')

    def test_db_skip_way_not_in_db(self, db_conn, poly05_filename):
        osm_elements = """
        <node id="1" lat="3.0" lon="3.0" user="test_user" uid="1" version="1" changeset="1" timestamp="2025-01-01T00:00:00Z">
            <tag k="highway" v="traffic_signals"/>
        </node>
        """.strip()
        osc_actions = """
        <delete>
            <way id="1" user="test_user" uid="1" version="2" changeset="2" timestamp="2025-01-02T00:00:00Z" />
        </delete>
        """.strip()

        elem = self.perform(db_conn.info.dbname, osm_elements, poly05_filename, osc_actions)
        assert not elem.xpath('.//way[@id="1"]')

    def test_osc_any_action_in_osc_other_way_included(self, db_conn, poly05_filename):
        """
        It might happen that way doesn't exist yet, but .osc might contain it (create/modify)
        We should keep all related actions to that object (e.g. historical reason) and delete it also
        if it should be deleted, because previous actions can create it.
        """
        osm_elements = """
        <node id="1" lat="3.0" lon="3.0" user="test_user" uid="1" version="1" changeset="1" timestamp="2025-01-01T00:00:00Z">
            <tag k="highway" v="traffic_signals"/>
        </node>
        """.strip()
        osc_actions = """
        <modify>
            <way id="1" user="test_user" uid="1" version="2" changeset="2" timestamp="2025-01-03T00:00:00Z">
                <nd ref="1"/>
                <nd ref="4"/>
                <tag k="highway" v="service"/>
            </way>
        </modify>
        <delete>
            <way id="1" user="test_user" uid="1" version="3" changeset="3" timestamp="2025-01-02T00:00:00Z" />
        </delete>
        """.strip()

        elem = self.perform(db_conn.info.dbname, osm_elements, poly05_filename, osc_actions)
        assert elem.xpath('.//way[@id="1"]')

    def test_osc_skip_all_actions_in_osc_way_not_included(self, db_conn, poly05_filename):
        osm_elements = """
        <node id="1" lat="3.0" lon="3.0" user="test_user" uid="1" version="1" changeset="1" timestamp="2025-01-01T00:00:00Z">
            <tag k="highway" v="traffic_signals"/>
        </node>
        """.strip()
        osc_actions = """
        <modify>
            <way id="1" user="test_user" uid="1" version="2" changeset="2" timestamp="2025-01-03T00:00:00Z">
                <nd ref="2"/>
                <nd ref="4"/>
                <tag k="highway" v="service"/>
            </way>
        </modify>
        <delete>
            <way id="1" user="test_user" uid="1" version="3" changeset="3" timestamp="2025-01-02T00:00:00Z" />
        </delete>
        """.strip()

        elem = self.perform(db_conn.info.dbname, osm_elements, poly05_filename, osc_actions)
        assert not elem.xpath('.//way[@id="1"]')


class TestOscPolyFilterRelationCreate(BaseOscPolyFilter):
    def test_db_member_node_in_db_and_area(self, db_conn, poly05_filename):
        osm_elements = """
        <node id="1" lat="3.0" lon="3.0" user="test_user" uid="1" version="1" changeset="1" timestamp="2025-01-01T00:00:00Z">
            <tag k="highway" v="traffic_signals"/>
        </node>
        """.strip()
        osc_actions = """
        <create>
            <relation id="1" user="test_user" uid="1" version="1" changeset="2" timestamp="2025-01-02T00:00:00Z">
                <member type="node" ref="1" role=""/>
                <member type="node" ref="2" role=""/>
                <tag k="type" v="site"/>
            </relation>
        </create>
        """.strip()

        elem = self.perform(db_conn.info.dbname, osm_elements, poly05_filename, osc_actions)
        assert elem.xpath('.//relation[@id="1"]')

    def test_db_skip_member_node_in_db_but_not_in_area(self, db_conn, poly05_filename):
        osm_elements = """
        <node id="1" lat="7.0" lon="7.0" user="test_user" uid="1" version="1" changeset="1" timestamp="2025-01-01T00:00:00Z">
            <tag k="highway" v="traffic_signals"/>
        </node>
        """.strip()
        osc_actions = """
        <create>
            <relation id="1" user="test_user" uid="1" version="1" changeset="2" timestamp="2025-01-02T00:00:00Z">
                <member type="node" ref="1" role=""/>
                <member type="node" ref="2" role=""/>
                <tag k="type" v="site"/>
            </relation>
        </create>
        """.strip()

        elem = self.perform(db_conn.info.dbname, osm_elements, poly05_filename, osc_actions)
        assert not elem.xpath('.//relation[@id="1"]')

    def test_db_member_way_in_db(self, db_conn, poly05_filename):
        osm_elements = """
        <node id="1" lat="7.0" lon="7.0" user="test_user" uid="1" version="1" changeset="1" timestamp="2025-01-01T00:00:00Z">
            <tag k="highway" v="traffic_signals"/>
        </node>
        <way id="1" user="test_user" uid="1" version="1" changeset="1" timestamp="2025-01-01T00:00:00Z">
            <nd ref="2"/>
            <nd ref="3"/>
        </way>
        """.strip()
        osc_actions = """
        <create>
            <relation id="1" user="test_user" uid="1" version="1" changeset="2" timestamp="2025-01-02T00:00:00Z">
                <member type="way" ref="1" role=""/>
                <tag k="type" v="route"/>
            </relation>
        </create>
        """.strip()

        elem = self.perform(db_conn.info.dbname, osm_elements, poly05_filename, osc_actions)
        assert elem.xpath('.//relation[@id="1"]')

    def test_db_member_relation_in_db(self, db_conn, poly05_filename):
        osm_elements = """
        <way id="1" user="test_user" uid="1" version="1" changeset="1" timestamp="2025-01-01T00:00:00Z">
            <nd ref="2"/>
            <nd ref="3"/>
        </way>
        <relation id="1" user="test_user" uid="1" version="1" changeset="1" timestamp="2025-01-01T00:00:00Z">
            <member type="way" ref="1" role=""/>
            <tag k="type" v="route"/>
        </relation>
        """.strip()
        osc_actions = """
        <create>
            <relation id="2" user="test_user" uid="1" version="1" changeset="2" timestamp="2025-01-02T00:00:00Z">
                <member type="relation" ref="1" role=""/>
                <tag k="type" v="route"/>
            </relation>
        </create>
        """.strip()

        elem = self.perform(db_conn.info.dbname, osm_elements, poly05_filename, osc_actions)
        assert elem.xpath('.//relation[@id="2"]')

    def test_db_skip_members_not_in_db(self, db_conn, poly05_filename):
        osm_elements = """
        <node id="1" lat="3.0" lon="3.0" user="test_user" uid="1" version="1" changeset="1" timestamp="2025-01-01T00:00:00Z">
            <tag k="highway" v="traffic_signals"/>
        </node>
        """.strip()
        osc_actions = """
        <create>
            <relation id="2" user="test_user" uid="1" version="1" changeset="1" timestamp="2025-01-01T00:00:00Z">
                <member type="node" ref="2" role=""/>
                <member type="way" ref="1" role=""/>
                <member type="relation" ref="1" role=""/>
                <tag k="type" v="site"/>
            </relation>
        </create>
        """.strip()

        elem = self.perform(db_conn.info.dbname, osm_elements, poly05_filename, osc_actions)
        assert not elem.xpath('.//relation[@id="2"]')

    def test_osc_member_node_included(self, db_conn, poly05_filename):
        """
        It might happen that node doesn't exist yet in area, but .osc might contain it (create/modify)
        """
        osm_elements = """
        <node id="1" lat="3.0" lon="3.0" user="test_user" uid="1" version="1" changeset="1" timestamp="2025-01-01T00:00:00Z">
            <tag k="highway" v="traffic_signals"/>
        </node>
        """.strip()
        osc_actions = """
        <create>
            <node id="3" lat="7.0" lon="3.0" user="test_user" uid="1" version="1" changeset="2" timestamp="2025-01-01T00:00:00Z">
                <tag k="highway" v="traffic_signals"/>
            </node>
        </create>
        <modify>
            <node id="3" lat="4.0" lon="3.0" user="test_user" uid="1" version="2" changeset="3" timestamp="2025-01-01T00:00:00Z">
                <tag k="highway" v="traffic_signals"/>
            </node>
        </modify>
        <modify>
            <node id="3" lat="7.0" lon="3.0" user="test_user" uid="1" version="3" changeset="4" timestamp="2025-01-01T00:00:00Z">
                <tag k="highway" v="traffic_signals"/>
            </node>
        </modify>
        <create>
            <relation id="1" user="test_user" uid="1" version="1" changeset="2" timestamp="2025-01-02T00:00:00Z">
                <member type="node" ref="2" role=""/>
                <member type="node" ref="3" role=""/>
                <tag k="type" v="site"/>
            </relation>
        </create>
        """.strip()

        elem = self.perform(db_conn.info.dbname, osm_elements, poly05_filename, osc_actions)
        assert elem.xpath('.//relation[@id="1"]')

    def test_osc_member_way_included(self, db_conn, poly05_filename):
        """
        It might happen that way doesn't exist yet in area, but .osc might contain it (create/modify)
        """
        osm_elements = """
        <node id="1" lat="3.0" lon="3.0" user="test_user" uid="1" version="1" changeset="1" timestamp="2025-01-01T00:00:00Z">
            <tag k="highway" v="traffic_signals"/>
        </node>
        """.strip()
        osc_actions = """
        <create>
            <way id="1" user="test_user" uid="1" version="1" changeset="2" timestamp="2025-01-01T00:00:00Z">
                <nd ref="2"/>
                <nd ref="3"/>
                <tag k="highway" v="residential"/>
            </way>
        </create>
        <modify>
            <way id="1" user="test_user" uid="1" version="2" changeset="3" timestamp="2025-01-01T00:00:00Z">
                <nd ref="1"/>
                <nd ref="2"/>
                <nd ref="3"/>
                <tag k="highway" v="residential"/>
            </way>
        </modify>
        <modify>
            <way id="1" user="test_user" uid="1" version="3" changeset="4" timestamp="2025-01-01T00:00:00Z">
                <nd ref="2"/>
                <nd ref="3"/>
                <tag k="highway" v="residential"/>
            </way>
        </modify>
        <create>
            <relation id="1" user="test_user" uid="1" version="1" changeset="5" timestamp="2025-01-02T00:00:00Z">
                <member type="way" ref="1" role=""/>
                <tag k="type" v="route"/>
            </relation>
        </create>
        """.strip()

        elem = self.perform(db_conn.info.dbname, osm_elements, poly05_filename, osc_actions)
        assert elem.xpath('.//relation[@id="1"]')

    def test_osc_member_relation_included(self, db_conn, poly05_filename):
        """
        It might happen that relation doesn't exist yet in area, but .osc might contain it (create/modify)
        """
        osm_elements = """
        <node id="1" lat="3.0" lon="3.0" user="test_user" uid="1" version="1" changeset="1" timestamp="2025-01-01T00:00:00Z">
            <tag k="highway" v="traffic_signals"/>
        </node>
        """.strip()
        osc_actions = """
        <create>
            <relation id="1" user="test_user" uid="1" version="1" changeset="2" timestamp="2025-01-02T00:00:00Z">
                <member type="node" ref="5" role=""/>
                <tag k="type" v="route"/>
            </relation>
        </create>
        <modify>
            <relation id="1" user="test_user" uid="1" version="2" changeset="3" timestamp="2025-01-02T00:00:00Z">
                <member type="node" ref="1" role=""/>
                <tag k="type" v="route"/>
            </relation>
        </modify>
        <modify>
            <relation id="1" user="test_user" uid="1" version="3" changeset="4" timestamp="2025-01-02T00:00:00Z">
                <member type="node" ref="5" role=""/>
                <tag k="type" v="route"/>
            </relation>
        </modify>
        <create>
            <relation id="2" user="test_user" uid="1" version="1" changeset="5" timestamp="2025-01-02T00:00:00Z">
                <member type="relation" ref="1" role=""/>
                <tag k="type" v="route"/>
            </relation>
        </create>
        """.strip()

        elem = self.perform(db_conn.info.dbname, osm_elements, poly05_filename, osc_actions)
        assert elem.xpath('.//relation[@id="2"]')

    def test_osc_skip_members_not_included(self, db_conn, poly05_filename):
        """
        It might happen that relation doesn't exist yet in area, but .osc might contain it (create/modify)
        """
        osm_elements = """
        <node id="1" lat="3.0" lon="3.0" user="test_user" uid="1" version="1" changeset="1" timestamp="2025-01-01T00:00:00Z">
            <tag k="highway" v="traffic_signals"/>
        </node>
        """.strip()
        osc_actions = """
        <create>
            <node id="2" lat="6.0" lon="6.0" user="test_user" uid="1" version="1" changeset="1" timestamp="2025-01-01T00:00:00Z">
                <tag k="highway" v="traffic_signals"/>
            </node>
            <way id="1" user="test_user" uid="1" version="1" changeset="2" timestamp="2025-01-01T00:00:00Z">
                <nd ref="2"/>
                <nd ref="3"/>
                <tag k="highway" v="residential"/>
            </way>
            <relation id="1" user="test_user" uid="1" version="1" changeset="2" timestamp="2025-01-02T00:00:00Z">
                <member type="way" ref="1" role=""/>
                <tag k="type" v="route"/>
            </relation>
        </create>
        <create>
            <relation id="2" user="test_user" uid="1" version="1" changeset="5" timestamp="2025-01-02T00:00:00Z">
                <member type="node" ref="2" role=""/>
                <member type="way" ref="1" role=""/>
                <member type="relation" ref="1" role=""/>
                <tag k="type" v="route"/>
            </relation>
        </create>
        """.strip()

        elem = self.perform(db_conn.info.dbname, osm_elements, poly05_filename, osc_actions)
        assert not elem.xpath('.//relation[@id="2"]')


class TestOscPolyFilterRelationModify(BaseOscPolyFilter):
    def test_db_relation_in_db(self, db_conn, poly05_filename):
        osm_elements = """
        <node id="1" lat="3.0" lon="3.0" user="test_user" uid="1" version="1" changeset="1" timestamp="2025-01-01T00:00:00Z">
            <tag k="highway" v="traffic_signals"/>
        </node>
        <relation id="1" user="test_user" uid="1" version="1" changeset="1" timestamp="2025-01-01T00:00:00Z">
            <member type="node" ref="5" role=""/>
            <tag k="type" v="route"/>
        </relation>
        """.strip()
        osc_actions = """
        <modify>
            <relation id="1" user="test_user" uid="1" version="2" changeset="2" timestamp="2025-01-02T00:00:00Z">
                <member type="node" ref="5" role=""/>
                <member type="node" ref="6" role=""/>
                <tag k="type" v="site"/>
            </relation>
        </modify>
        """.strip()

        elem = self.perform(db_conn.info.dbname, osm_elements, poly05_filename, osc_actions)
        assert elem.xpath('.//relation[@id="1"]')

    def test_db_skip_relation_not_in_db(self, db_conn, poly05_filename):
        osm_elements = """
        <node id="1" lat="3.0" lon="3.0" user="test_user" uid="1" version="1" changeset="1" timestamp="2025-01-01T00:00:00Z">
            <tag k="highway" v="traffic_signals"/>
        </node>
        """.strip()
        osc_actions = """
        <modify>
            <relation id="1" user="test_user" uid="1" version="2" changeset="2" timestamp="2025-01-02T00:00:00Z">
                <member type="node" ref="5" role=""/>
                <tag k="type" v="site"/>
            </relation>
        </modify>
        """.strip()

        elem = self.perform(db_conn.info.dbname, osm_elements, poly05_filename, osc_actions)
        assert not elem.xpath('.//relation[@id="1"]')

    def test_db_member_node_in_db_and_area(self, db_conn, poly05_filename):
        osm_elements = """
        <node id="1" lat="3.0" lon="3.0" user="test_user" uid="1" version="1" changeset="1" timestamp="2025-01-01T00:00:00Z">
            <tag k="highway" v="traffic_signals"/>
        </node>
        """.strip()
        osc_actions = """
        <modify>
            <relation id="1" user="test_user" uid="1" version="2" changeset="2" timestamp="2025-01-02T00:00:00Z">
                <member type="node" ref="1" role=""/>
                <tag k="type" v="site"/>
            </relation>
        </modify>
        """.strip()

        elem = self.perform(db_conn.info.dbname, osm_elements, poly05_filename, osc_actions)
        assert elem.xpath('.//relation[@id="1"]')

    def test_db_skip_member_node_in_db_but_not_in_area(self, db_conn, poly05_filename):
        osm_elements = """
        <node id="1" lat="7.0" lon="7.0" user="test_user" uid="1" version="1" changeset="1" timestamp="2025-01-01T00:00:00Z">
            <tag k="highway" v="traffic_signals"/>
        </node>
        """.strip()
        osc_actions = """
        <modify>
            <relation id="1" user="test_user" uid="1" version="2" changeset="2" timestamp="2025-01-02T00:00:00Z">
                <member type="node" ref="1" role=""/>
                <tag k="type" v="site"/>
            </relation>
        </modify>
        """.strip()

        elem = self.perform(db_conn.info.dbname, osm_elements, poly05_filename, osc_actions)
        assert not elem.xpath('.//relation[@id="1"]')

    def test_db_member_way_in_db(self, db_conn, poly05_filename):
        osm_elements = """
        <way id="1" user="test_user" uid="1" version="1" changeset="1" timestamp="2025-01-01T00:00:00Z">
            <nd ref="2"/>
            <nd ref="3"/>
        </way>
        """.strip()
        osc_actions = """
        <modify>
            <relation id="1" user="test_user" uid="1" version="2" changeset="2" timestamp="2025-01-02T00:00:00Z">
                <member type="way" ref="1" role=""/>
                <tag k="type" v="route"/>
            </relation>
        </modify>
        """.strip()

        elem = self.perform(db_conn.info.dbname, osm_elements, poly05_filename, osc_actions)
        assert elem.xpath('.//relation[@id="1"]')

    def test_db_member_relation_in_db(self, db_conn, poly05_filename):
        osm_elements = """
        <relation id="1" user="test_user" uid="1" version="1" changeset="1" timestamp="2025-01-01T00:00:00Z">
            <member type="node" ref="1" role=""/>
        </relation>
        """.strip()
        osc_actions = """
        <modify>
            <relation id="2" user="test_user" uid="1" version="2" changeset="2" timestamp="2025-01-02T00:00:00Z">
                <member type="relation" ref="1" role=""/>
                <tag k="type" v="route"/>
            </relation>
        </modify>
        """.strip()

        elem = self.perform(db_conn.info.dbname, osm_elements, poly05_filename, osc_actions)
        assert elem.xpath('.//relation[@id="2"]')

    def test_db_skip_members_not_in_db(self, db_conn, poly05_filename):
        osm_elements = """
        <node id="1" lat="7.0" lon="7.0" user="test_user" uid="1" version="1" changeset="1" timestamp="2025-01-01T00:00:00Z">
            <tag k="highway" v="traffic_signals"/>
        </node>
        """.strip()
        osc_actions = """
        <modify>
            <relation id="1" user="test_user" uid="1" version="2" changeset="2" timestamp="2025-01-02T00:00:00Z">
                <member type="node" ref="5" role=""/>
                <member type="way" ref="5" role=""/>
                <member type="relation" ref="5" role=""/>
                <tag k="type" v="route"/>
            </relation>
        </modify>
        """.strip()

        elem = self.perform(db_conn.info.dbname, osm_elements, poly05_filename, osc_actions)
        assert not elem.xpath('.//relation[@id="1"]')

    def test_osc_member_node_included(self, db_conn, poly05_filename):
        """
        It might happen that node doesn't exist yet in area, but .osc might contain it (create/modify)
        """
        osm_elements = """
        <node id="1" lat="3.0" lon="3.0" user="test_user" uid="1" version="1" changeset="1" timestamp="2025-01-01T00:00:00Z">
            <tag k="highway" v="traffic_signals"/>
        </node>
        """.strip()
        osc_actions = """
        <create>
            <node id="3" lat="7.0" lon="3.0" user="test_user" uid="1" version="1" changeset="2" timestamp="2025-01-01T00:00:00Z">
                <tag k="highway" v="traffic_signals"/>
            </node>
        </create>
        <modify>
            <node id="3" lat="4.0" lon="3.0" user="test_user" uid="1" version="2" changeset="3" timestamp="2025-01-01T00:00:00Z">
                <tag k="highway" v="traffic_signals"/>
            </node>
        </modify>
        <modify>
            <node id="3" lat="7.0" lon="3.0" user="test_user" uid="1" version="3" changeset="4" timestamp="2025-01-01T00:00:00Z">
                <tag k="highway" v="traffic_signals"/>
            </node>
        </modify>
        <modify>
            <relation id="1" user="test_user" uid="1" version="2" changeset="5" timestamp="2025-01-02T00:00:00Z">
                <member type="node" ref="2" role=""/>
                <member type="node" ref="3" role=""/>
                <tag k="type" v="site"/>
            </relation>
        </modify>
        <modify>
            <relation id="1" user="test_user" uid="1" version="3" changeset="6" timestamp="2025-01-02T00:00:00Z">
                <member type="node" ref="5" role=""/>
                <member type="node" ref="6" role=""/>
                <tag k="type" v="site"/>
            </relation>
        </modify>
        """.strip()

        elem = self.perform(db_conn.info.dbname, osm_elements, poly05_filename, osc_actions)
        assert elem.xpath('.//relation[@id="1"]')

    def test_osc_member_way_included(self, db_conn, poly05_filename):
        """
        It might happen that way doesn't exist yet in area, but .osc might contain it (create/modify)
        """
        osm_elements = """
        <node id="1" lat="3.0" lon="3.0" user="test_user" uid="1" version="1" changeset="1" timestamp="2025-01-01T00:00:00Z">
            <tag k="highway" v="traffic_signals"/>
        </node>
        """.strip()
        osc_actions = """
        <create>
            <way id="1" user="test_user" uid="1" version="1" changeset="2" timestamp="2025-01-01T00:00:00Z">
                <nd ref="2"/>
                <nd ref="3"/>
                <tag k="highway" v="residential"/>
            </way>
        </create>
        <modify>
            <way id="1" user="test_user" uid="1" version="2" changeset="3" timestamp="2025-01-01T00:00:00Z">
                <nd ref="1"/>
                <nd ref="2"/>
                <nd ref="3"/>
                <tag k="highway" v="residential"/>
            </way>
        </modify>
        <modify>
            <way id="1" user="test_user" uid="1" version="3" changeset="4" timestamp="2025-01-01T00:00:00Z">
                <nd ref="2"/>
                <nd ref="3"/>
                <tag k="highway" v="residential"/>
            </way>
        </modify>
        <modify>
            <relation id="1" user="test_user" uid="1" version="1" changeset="5" timestamp="2025-01-02T00:00:00Z">
                <member type="way" ref="1" role=""/>
                <tag k="type" v="route"/>
            </relation>
        </modify>
        <modify>
            <relation id="1" user="test_user" uid="1" version="2" changeset="6" timestamp="2025-01-02T00:00:00Z">
                <member type="way" ref="6" role=""/>
                <tag k="type" v="route"/>
            </relation>
        </modify>
        """.strip()

        elem = self.perform(db_conn.info.dbname, osm_elements, poly05_filename, osc_actions)
        assert elem.xpath('.//relation[@id="1"]')

    def test_osc_member_relation_included(self, db_conn, poly05_filename):
        """
        It might happen that relation doesn't exist yet in area, but .osc might contain it (create/modify)
        """
        osm_elements = """
        <node id="1" lat="3.0" lon="3.0" user="test_user" uid="1" version="1" changeset="1" timestamp="2025-01-01T00:00:00Z">
            <tag k="highway" v="traffic_signals"/>
        </node>
        """.strip()
        osc_actions = """
        <create>
            <relation id="1" user="test_user" uid="1" version="1" changeset="2" timestamp="2025-01-02T00:00:00Z">
                <member type="node" ref="5" role=""/>
                <tag k="type" v="route"/>
            </relation>
        </create>
        <modify>
            <relation id="1" user="test_user" uid="1" version="2" changeset="3" timestamp="2025-01-02T00:00:00Z">
                <member type="node" ref="1" role=""/>
                <tag k="type" v="route"/>
            </relation>
        </modify>
        <modify>
            <relation id="1" user="test_user" uid="1" version="3" changeset="4" timestamp="2025-01-02T00:00:00Z">
                <member type="node" ref="5" role=""/>
                <tag k="type" v="route"/>
            </relation>
        </modify>
        <modify>
            <relation id="2" user="test_user" uid="1" version="2" changeset="5" timestamp="2025-01-02T00:00:00Z">
                <member type="relation" ref="1" role=""/>
                <tag k="type" v="route"/>
            </relation>
        </modify>
        <modify>
            <relation id="2" user="test_user" uid="1" version="3" changeset="5" timestamp="2025-01-02T00:00:00Z">
                <member type="relation" ref="6" role=""/>
                <tag k="type" v="route"/>
            </relation>
        </modify>
        """.strip()

        elem = self.perform(db_conn.info.dbname, osm_elements, poly05_filename, osc_actions)
        assert elem.xpath('.//relation[@id="2"]')

    def test_osc_skip_members_not_included(self, db_conn, poly05_filename):
        """
        It might happen that relation doesn't exist yet in area, but .osc might contain it (create/modify)
        """
        osm_elements = """
        <node id="1" lat="3.0" lon="3.0" user="test_user" uid="1" version="1" changeset="1" timestamp="2025-01-01T00:00:00Z">
            <tag k="highway" v="traffic_signals"/>
        </node>
        """.strip()
        osc_actions = """
        <create>
            <node id="2" lat="6.0" lon="6.0" user="test_user" uid="1" version="1" changeset="1" timestamp="2025-01-01T00:00:00Z">
                <tag k="highway" v="traffic_signals"/>
            </node>
            <way id="1" user="test_user" uid="1" version="1" changeset="2" timestamp="2025-01-01T00:00:00Z">
                <nd ref="2"/>
                <nd ref="3"/>
                <tag k="highway" v="residential"/>
            </way>
            <relation id="1" user="test_user" uid="1" version="1" changeset="2" timestamp="2025-01-02T00:00:00Z">
                <member type="way" ref="1" role=""/>
                <tag k="type" v="route"/>
            </relation>
        </create>
        <modify>
            <relation id="2" user="test_user" uid="1" version="1" changeset="5" timestamp="2025-01-02T00:00:00Z">
                <member type="node" ref="2" role=""/>
                <member type="way" ref="1" role=""/>
                <member type="relation" ref="1" role=""/>
                <tag k="type" v="route"/>
            </relation>
        </modify>
        """.strip()

        elem = self.perform(db_conn.info.dbname, osm_elements, poly05_filename, osc_actions)
        assert not elem.xpath('.//relation[@id="2"]')

    def test_osc_any_action_in_osc_other_relation_included(self, db_conn, poly05_filename):
        """
        It might happen that node/way doesn't exist yet in area, but .osc might contain it (create/modify)
        """
        osm_elements = """
        <node id="1" lat="3.0" lon="3.0" user="test_user" uid="1" version="1" changeset="1" timestamp="2025-01-01T00:00:00Z">
            <tag k="highway" v="traffic_signals"/>
        </node>
        """.strip()
        osc_actions = """
        <create>
            <relation id="1" user="test_user" uid="1" version="1" changeset="2" timestamp="2025-01-02T00:00:00Z">
                <member type="node" ref="5" role=""/>
                <tag k="type" v="route"/>
            </relation>
        </create>
        <modify>
            <relation id="1" user="test_user" uid="1" version="2" changeset="3" timestamp="2025-01-02T00:00:00Z">
                <member type="node" ref="1" role=""/>
                <tag k="type" v="route"/>
            </relation>
        </modify>
        <modify>
            <relation id="1" user="test_user" uid="1" version="3" changeset="4" timestamp="2025-01-02T00:00:00Z">
                <member type="node" ref="5" role=""/>
                <tag k="type" v="route"/>
            </relation>
        </modify>
        """.strip()

        elem = self.perform(db_conn.info.dbname, osm_elements, poly05_filename, osc_actions)
        assert elem.xpath('.//relation[@id="1"]')

    def test_osc_skip_all_actions_in_osc_relation_not_included(self, db_conn, poly05_filename):
        """
        It might happen that node/way doesn't exist yet in area, but .osc might contain it (create/modify)
        """
        osm_elements = """
        <node id="1" lat="3.0" lon="3.0" user="test_user" uid="1" version="1" changeset="1" timestamp="2025-01-01T00:00:00Z">
            <tag k="highway" v="traffic_signals"/>
        </node>
        """.strip()
        osc_actions = """
        <create>
            <relation id="1" user="test_user" uid="1" version="1" changeset="2" timestamp="2025-01-02T00:00:00Z">
                <member type="node" ref="5" role=""/>
                <tag k="type" v="route"/>
            </relation>
        </create>
        <modify>
            <relation id="1" user="test_user" uid="1" version="2" changeset="3" timestamp="2025-01-02T00:00:00Z">
                <member type="node" ref="7" role=""/>
                <tag k="type" v="route"/>
            </relation>
        </modify>
        <modify>
            <relation id="1" user="test_user" uid="1" version="3" changeset="4" timestamp="2025-01-02T00:00:00Z">
                <member type="node" ref="5" role=""/>
                <tag k="type" v="route"/>
            </relation>
        </modify>
        """.strip()

        elem = self.perform(db_conn.info.dbname, osm_elements, poly05_filename, osc_actions)
        assert not elem.xpath('.//relation[@id="1"]')


class TestOscPolyFilterRelationDelete(BaseOscPolyFilter):
    def test_db_relation_in_db(self, db_conn, poly05_filename):
        osm_elements = """
        <node id="1" lat="3.0" lon="3.0" user="test_user" uid="1" version="1" changeset="1" timestamp="2025-01-01T00:00:00Z">
            <tag k="highway" v="traffic_signals"/>
        </node>
        <relation id="1" user="test_user" uid="1" version="1" changeset="1" timestamp="2025-01-01T00:00:00Z">
            <member type="node" ref="5" role=""/>
            <tag k="type" v="route"/>
        </relation>
        """.strip()
        osc_actions = """
        <delete>
            <relation id="1" user="test_user" uid="1" version="2" changeset="2" timestamp="2025-01-02T00:00:00Z"/>
        </delete>
        """.strip()

        elem = self.perform(db_conn.info.dbname, osm_elements, poly05_filename, osc_actions)
        assert elem.xpath('.//relation[@id="1"]')

    def test_db_skip_relation_not_in_db(self, db_conn, poly05_filename):
        osm_elements = """
            <node id="1" lat="3.0" lon="3.0" user="test_user" uid="1" version="1" changeset="1" timestamp="2025-01-01T00:00:00Z">
                <tag k="highway" v="traffic_signals"/>
            </node>
            """.strip()
        osc_actions = """
            <delete>
                <relation id="1" user="test_user" uid="1" version="2" changeset="2" timestamp="2025-01-02T00:00:00Z"/>
            </delete>
            """.strip()

        elem = self.perform(db_conn.info.dbname, osm_elements, poly05_filename, osc_actions)
        assert not elem.xpath('.//relation[@id="1"]')

    def test_osc_any_action_in_osc_other_relation_included(self, db_conn, poly05_filename):
        """
        It might happen that relation doesn't exist yet, but .osc might contain it (create/modify)
        We should keep all related actions to that object (e.g. historical reason) and delete it also
        if it should be deleted, because previous actions can create it.
        """
        osm_elements = """
        <node id="1" lat="3.0" lon="3.0" user="test_user" uid="1" version="1" changeset="1" timestamp="2025-01-01T00:00:00Z">
            <tag k="highway" v="traffic_signals"/>
        </node>
        """.strip()
        osc_actions = """
        <create>
            <relation id="1" user="test_user" uid="1" version="1" changeset="2" timestamp="2025-01-02T00:00:00Z">
                <member type="node" ref="5" role=""/>
                <tag k="type" v="route"/>
            </relation>
        </create>
        <modify>
            <relation id="1" user="test_user" uid="1" version="2" changeset="3" timestamp="2025-01-02T00:00:00Z">
                <member type="node" ref="1" role=""/>
                <tag k="type" v="route"/>
            </relation>
        </modify>
        <modify>
            <relation id="1" user="test_user" uid="1" version="2" changeset="3" timestamp="2025-01-02T00:00:00Z">
                <member type="node" ref="6" role=""/>
                <tag k="type" v="route"/>
            </relation>
        </modify>
        <delete>
            <relation id="1" user="test_user" uid="1" version="3" changeset="4" timestamp="2025-01-02T00:00:00Z"/>
        </delete>
        """.strip()

        elem = self.perform(db_conn.info.dbname, osm_elements, poly05_filename, osc_actions)
        assert elem.xpath('.//relation[@id="1"]')

    def test_osc_skip_all_actions_in_osc_relation_not_included(self, db_conn, poly05_filename):
        """
        It might happen that relation doesn't exist yet, but .osc might contain it (create/modify)
        We should keep all related actions to that object (e.g. historical reason) and delete it also
        if it should be deleted, because previous actions can create it.
        """
        osm_elements = """
        <node id="1" lat="3.0" lon="3.0" user="test_user" uid="1" version="1" changeset="1" timestamp="2025-01-01T00:00:00Z">
            <tag k="highway" v="traffic_signals"/>
        </node>
        """.strip()
        osc_actions = """
        <create>
            <relation id="1" user="test_user" uid="1" version="1" changeset="2" timestamp="2025-01-02T00:00:00Z">
                <member type="node" ref="5" role=""/>
                <tag k="type" v="route"/>
            </relation>
        </create>
        <modify>
            <relation id="1" user="test_user" uid="1" version="2" changeset="3" timestamp="2025-01-02T00:00:00Z">
                <member type="node" ref="3" role=""/>
                <tag k="type" v="route"/>
            </relation>
        </modify>
        <modify>
            <relation id="1" user="test_user" uid="1" version="2" changeset="3" timestamp="2025-01-02T00:00:00Z">
                <member type="node" ref="6" role=""/>
                <tag k="type" v="route"/>
            </relation>
        </modify>
        <delete>
            <relation id="1" user="test_user" uid="1" version="3" changeset="4" timestamp="2025-01-02T00:00:00Z"/>
        </delete>
        """.strip()

        elem = self.perform(db_conn.info.dbname, osm_elements, poly05_filename, osc_actions)
        assert not elem.xpath('.//relation[@id="1"]')
