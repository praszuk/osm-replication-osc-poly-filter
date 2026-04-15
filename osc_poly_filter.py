import argparse
import enum
import numpy as np
import gzip
import os

import psycopg
from typing import TypeAlias

from lxml import etree
from shapely import unary_union, points as shapely_points, covers, Geometry
from shapely.geometry import Polygon, MultiPolygon


OSMObjectId: TypeAlias = int
InDb: TypeAlias = bool
InPoly: TypeAlias = bool
Lat: TypeAlias = float
Lon: TypeAlias = float

NODES_TABLE_NAME = 'planet_osm_nodes'
WAYS_TABLE_NAME = 'planet_osm_ways'
RELATIONS_TABLE_NAME = 'planet_osm_rels'


nodes_to_get_from_db: set[OSMObjectId] = set()
nodes_lat_lon_to_verify_in_poly: set[tuple[OSMObjectId, Lat, Lon]] = set()
"""
id,lat,lon tuple as key to store all found version of nodes 
"""

ways_to_get_from_db: set[OSMObjectId] = set()
relations_to_get_from_db: set[OSMObjectId] = set()

nodes_to_include: dict[OSMObjectId, tuple[InDb, InPoly]] = {}
ways_to_include: set[OSMObjectId] = set()
relations_to_include: set[OSMObjectId] = set()


class OsmObjectType(str, enum.Enum):
    NODE = 'node'
    WAY = 'way'
    RELATION = 'relation'


class PolyGeomHandler:
    def __init__(self):
        self.geom: Geometry | None = None

    def in_poly(self, coordinates: list[tuple[Lat, Lon]]) -> np.typing.NDArray[np.bool_]:
        """
        :return: list of bools where index corresponds to input list coordinates
        """
        xs = np.fromiter((lon for lat, lon in coordinates), dtype=float)
        ys = np.fromiter((lat for lat, lon in coordinates), dtype=float)
        mask = covers(self.geom, shapely_points(xs, ys))
        return mask

    def load_poly(self, filename: str) -> None:
        polygons = []
        holes = []

        with open(filename) as f:
            lines = iter(f)
            next(lines)  # skip name

            ring = None
            is_hole_ring = False

            for raw_line in lines:
                line = raw_line.strip()
                if not line:
                    continue

                if line == 'END':
                    if ring is None:
                        break
                    polygon = Polygon(ring)
                    if is_hole_ring:
                        holes.append(polygon)
                    else:
                        polygons.append(polygon)

                    ring = None
                    continue

                parts = line.split()
                # coordinates
                if len(parts) == 2:
                    lon, lat = map(float, parts)
                    ring.append((lon, lat))  # noqa
                    continue

                # name of section
                is_hole_ring = parts[0].startswith('!')
                ring = []

        geom = unary_union(polygons)
        if holes:
            geom = geom.difference(unary_union(holes))

        if geom.geom_type == 'Polygon':
            geom = MultiPolygon([geom])  # noqa

        self.geom = geom


poly_geom_handler = PolyGeomHandler()


def open_input(filename: str):
    if filename.endswith('.gz'):
        return gzip.open(filename, 'rb')
    return open(filename, 'rb')


def open_output(filename: str):
    if filename.endswith('.gz'):
        return gzip.open(filename, 'wb')
    return open(filename, 'wb')


def iter_osmchange(filename: str, tags: tuple[str, ...]):
    with open_input(filename) as f:
        context = etree.iterparse(f, events=('end',), tag=tags, recover=True)
        for event, elem in context:
            action = elem.getparent().tag
            yield action, elem

            # free memory
            elem.clear()
            while elem.getprevious() is not None:
                del elem.getparent()[0]


def load_object_ids(filename: str) -> None:
    for action, elem in iter_osmchange(
        filename, tags=(OsmObjectType.NODE, OsmObjectType.WAY, OsmObjectType.RELATION)
    ):
        obj_id = int(elem.attrib['id'])
        if elem.tag == OsmObjectType.NODE:
            # In some .osc files 'delete' action might not contain lat/lon for nodes
            if 'lat' in elem.attrib:
                nodes_lat_lon_to_verify_in_poly.add(
                    (obj_id, float(elem.attrib['lat']), float(elem.attrib['lon']))
                )
            # Add all nodes to get_from_db, to ensure we will check all versions of node (lat lon)
            nodes_to_get_from_db.add(obj_id)
        elif elem.tag == OsmObjectType.WAY:
            ways_to_get_from_db.add(obj_id)
            for nd in elem.iterfind('nd'):
                nodes_to_get_from_db.add(int(nd.attrib['ref']))
        elif elem.tag == OsmObjectType.RELATION:
            relations_to_get_from_db.add(obj_id)
            for member in elem.iterfind('member'):
                ref = int(member.get('ref'))
                match member.get('type'):
                    case OsmObjectType.NODE:
                        nodes_to_get_from_db.add(ref)
                    case OsmObjectType.WAY:
                        ways_to_get_from_db.add(ref)
                    case OsmObjectType.RELATION:
                        relations_to_get_from_db.add(ref)


def iter_chunk(data, size):
    for i in range(0, len(data), size):
        yield data[i : i + size]


def fetch_missing_lat_lon_of_nodes_from_db(conn) -> None:
    for node_ids in iter_chunk(list(nodes_to_get_from_db), 1000):
        query = f"""
            SELECT id, lat / 1e7 AS lat_float, lon / 1e7 AS lon_float
            FROM {NODES_TABLE_NAME}
            WHERE id = ANY(%s)
        """
        with conn.cursor() as cursor:
            cursor.execute(query, (node_ids,))
            for osm_id, lat, lon in cursor.fetchall():
                nodes_lat_lon_to_verify_in_poly.add((osm_id, float(lat), float(lon)))

                node_to_include = nodes_to_include.get(osm_id, (False, False))
                nodes_to_include[osm_id] = (True, node_to_include[1])


def check_nodes_in_poly_to_include() -> None:
    obj_ids = []
    lat_lons = []
    # Note: it iterates over all nodes – including nodes classified as included (fetched from db)
    # It's needed due to different logic for determining if way should be
    # included (based on condition in area and optionally in db) – it's not needed for nodes
    for node_id, lat, lon in nodes_lat_lon_to_verify_in_poly:
        obj_ids.append(node_id)
        lat_lons.append((lat, lon))

    in_poly_results = poly_geom_handler.in_poly(lat_lons)
    for osm_id, is_in_poly in zip(obj_ids, in_poly_results):
        # OR to keep True (as included) for any version
        node_to_include = nodes_to_include.get(osm_id, (False, False))
        nodes_to_include[osm_id] = (node_to_include[0], node_to_include[1] or is_in_poly)


def check_ways_from_db_to_include(conn) -> None:
    for way_ids in iter_chunk(list(ways_to_get_from_db), 1000):
        query = f"""
            SELECT id 
            FROM {WAYS_TABLE_NAME}
            WHERE id = ANY(%s)
        """
        with conn.cursor() as cursor:
            cursor.execute(query, (way_ids,))
            for result in cursor.fetchall():
                ways_to_include.add(int(result[0]))


def check_relations_from_db_to_include(conn) -> None:
    for relation_ids in iter_chunk(list(relations_to_get_from_db), 1000):
        query = f"""
            SELECT id 
            FROM {RELATIONS_TABLE_NAME}
            WHERE id = ANY(%s)
        """
        with conn.cursor() as cursor:
            cursor.execute(query, (relation_ids,))
            for result in cursor.fetchall():
                relations_to_include.add(int(result[0]))


def check_ways_and_relation_from_objects_to_include(filename: str) -> None:
    for action, elem in iter_osmchange(filename, tags=(OsmObjectType.WAY, OsmObjectType.RELATION)):
        obj_id = int(elem.attrib['id'])

        if elem.tag == OsmObjectType.WAY and obj_id not in ways_to_include:
            if any(  # any way node in poly
                nodes_to_include.get(int(nd.attrib['ref']), (False, False))[1]
                for nd in elem.iterfind('nd')
            ):
                ways_to_include.add(obj_id)

        elif elem.tag == OsmObjectType.RELATION and obj_id not in relations_to_include:
            is_any_member_included = False

            for member in elem.iterfind('member'):
                ref = int(member.get('ref'))
                match member.get('type'):
                    case OsmObjectType.NODE:
                        if nodes_to_include.get(ref, (False, False))[1]:
                            is_any_member_included = True
                            break
                    case OsmObjectType.WAY:
                        if ref in ways_to_include:
                            is_any_member_included = True
                            break
                    case OsmObjectType.RELATION:
                        if ref in relations_to_include:
                            is_any_member_included = True
                            break

            if is_any_member_included:
                relations_to_include.add(obj_id)


def filter_and_output_with_include_ids(input_filename: str, output_filename: str) -> None:
    with open_output(output_filename) as f:
        with etree.xmlfile(f, encoding='utf-8') as xml_out:
            xml_out.write_declaration()

            with xml_out.element('osmChange', version='0.6', generator='osc_poly_filter/0.1'):
                osm_obj_elements_to_save = []
                for _, action_elem in iter_osmchange(
                    input_filename, tags=('create', 'modify', 'delete')
                ):
                    action = action_elem.tag

                    for elem in action_elem:
                        obj_id = int(elem.attrib['id'])
                        if elem.tag == OsmObjectType.NODE:
                            if action == 'create':
                                should_include = nodes_to_include.get(obj_id, (False, False))[1]
                            else:
                                # node doesn't need to be in poly to include it on modify/delete
                                # it can be just in db
                                # it need to be in poly for ways and relations
                                should_include = any(nodes_to_include.get(obj_id, (False, False)))
                        elif elem.tag == OsmObjectType.WAY:
                            should_include = obj_id in ways_to_include
                        elif elem.tag == OsmObjectType.RELATION:
                            should_include = obj_id in relations_to_include
                        else:
                            continue
                        if should_include:
                            osm_obj_elements_to_save.append(elem)

                    if len(osm_obj_elements_to_save) > 0:
                        xml_out.write('\n')
                        with xml_out.element(action):
                            for osm_obj_elem in osm_obj_elements_to_save:
                                xml_out.write(osm_obj_elem)
                        osm_obj_elements_to_save.clear()

                    action_elem.clear()


def main():
    parser = argparse.ArgumentParser(
        description='Filter OSM changes from .osc[.gz] for .poly area.'
    )
    parser.add_argument('input', help='input .osc or .osc.gz file')
    parser.add_argument('output', help='output .osc or .osc.gz file')
    parser.add_argument('--db-name', dest='db_name', help='Database name')
    parser.add_argument('--db-host', dest='db_host', help='Database host')
    parser.add_argument('--db-port', dest='db_port', type=int, help='Database port')
    parser.add_argument('--db-user', help='Database user')
    parser.add_argument('--poly', help='osmosis polygon file')
    options = parser.parse_args()
    db_pass = os.environ['POSTGRES_PASSWORD']

    poly_geom_handler.load_poly(options.poly)

    # Step 1: Read all osm object ids (and lat lon for nodes) from .osc and keep in collections
    load_object_ids(options.input)

    # Step 2: Fetch nodes with missing lat lon from db and verify all nodes (all versions) if they are inside the poly
    # For same node id, one version is enough to include specific node
    with psycopg.connect(
        f'host={options.db_host}'
        f' port={options.db_port}'
        f' dbname={options.db_name}'
        f' user={options.db_user}'
        f' password={db_pass}'
    ) as conn:
        fetch_missing_lat_lon_of_nodes_from_db(conn)
        check_nodes_in_poly_to_include()

        # Step 3: Check if ways and relations are in db to mark them as included
        check_ways_from_db_to_include(conn)
        check_relations_from_db_to_include(conn)

    # Step 4: Iterate again over .osc (skipping nodes) – check for ways and relation (not in db) if they should be included
    # Additional iteration, to check if any version should be included (then we will include all)
    check_ways_and_relation_from_objects_to_include(options.input)

    # Step 5: Iterate again over .osc – final filter (using to include)
    filter_and_output_with_include_ids(options.input, options.output)


if __name__ == '__main__':
    main()
