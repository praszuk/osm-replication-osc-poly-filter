import argparse
import numpy as np

from shapely import unary_union, points as shapely_points, covers, Geometry
from shapely.geometry import Polygon, MultiPolygon


class PolyGeomHandler:
    def __init__(self):
        self.geom: Geometry | None = None

    def in_poly(self, coordinates: list[tuple[float, float]]) -> np.typing.NDArray[np.bool_]:
        """
        :param coordinates: lat lon
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
