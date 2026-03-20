import argparse

from shapely import unary_union, Point
from shapely.geometry import Polygon, MultiPolygon
from shapely.prepared import prep, PreparedGeometry


class PolyGeomHandler:
    def __init__(self):
        self.prepared_poly: PreparedGeometry | None = None

    def is_in_poly(self, lat: float, lon: float) -> bool:
        return self.prepared_poly.covers(Point(lon, lat))

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
                    ring.append((lon, lat))
                    continue

                # name of section
                is_hole_ring = parts[0].startswith('!')
                ring = []

        geom = unary_union(polygons)
        if holes:
            geom = geom.difference(unary_union(holes))

        if geom.geom_type == 'Polygon':
            geom = MultiPolygon([geom])  # noqa

        self.prepared_poly = prep(geom)


poly_geom_handler = PolyGeomHandler()


def main():
    parser = argparse.ArgumentParser(
        description='Filter OSM changes from .osc[.gz] for .poly area.'
    )
    parser.add_argument('input', help='input .osc or .osc.gz file')
    parser.add_argument('output', help='output .osc or .osc.gz file')
    parser.add_argument('--poly', help='osmosis polygon file')
    options = parser.parse_args()

    poly_geom_handler.load_poly(options.poly)


if __name__ == '__main__':
    main()
