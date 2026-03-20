import tempfile

from osc_poly_filter import PolyGeomHandler


class TestLoadPoly:
    def test_simple_polygon(self):
        # fmt: off
        content = (
            'square\n'
            '1\n'
            '0 0\n'
            '0 2\n'
            '2 2\n'
            '2 0\n'
            '0 0\n'
            'END\n'
            'END\n'
        )
        # fmt: on
        with tempfile.NamedTemporaryFile(mode='w+', suffix='.poly') as f:
            f.write(content)
            f.flush()

            poly_geom_handler: PolyGeomHandler = PolyGeomHandler()
            poly_geom_handler.load_poly(f.name)

            assert poly_geom_handler.is_in_poly(0, 0)  # edge/point
            assert poly_geom_handler.is_in_poly(0.1, 0.1)
            assert poly_geom_handler.is_in_poly(1, 1)

            assert not poly_geom_handler.is_in_poly(-1, -1)
            assert not poly_geom_handler.is_in_poly(3, 3)

    def test_multipolygon_two_areas(self):
        # fmt: off
        content = (
            'multipolygon_data\n'
            'area1\n'
            '0 0\n'
            '0 1\n'
            '1 1\n'
            '1 0\n'
            '0 0\n'
            'END\n'
            'area2\n'
            '2 2\n'
            '2 3\n'
            '3 3\n'
            '3 2\n'
            '2 2\n'
            'END\n'
            'END\n'
        )
        # fmt: on
        with tempfile.NamedTemporaryFile(mode='w+', suffix='.poly') as f:
            f.write(content)
            f.flush()

            poly_geom_handler: PolyGeomHandler = PolyGeomHandler()
            poly_geom_handler.load_poly(f.name)

            # Inside area1
            assert poly_geom_handler.is_in_poly(0.5, 0.5)

            # Inside area2
            assert poly_geom_handler.is_in_poly(2.5, 2.5)

            # Outside both
            assert not poly_geom_handler.is_in_poly(1.5, 1.5)
            assert not poly_geom_handler.is_in_poly(3.5, 3.5)

    def test_multipolygon_with_holes(self):
        # fmt: off
        content = (
            'poly\n'
            'area1\n'
            '0 0\n'
            '0 3\n'
            '3 3\n'
            '3 0\n'
            '0 0\n'
            'END\n'
            '!hole1\n'
            '1 1\n'
            '1 2\n'
            '2 2\n'
            '2 1\n'
            '1 1\n'
            'END\n'
            'area2\n'
            '4 4\n'
            '4 5\n'
            '5 5\n'
            '5 4\n'
            '4 4\n'
            'END\n'
            'END\n'
        )
        # fmt: on
        with tempfile.NamedTemporaryFile(mode='w+', suffix='.poly') as f:
            f.write(content)
            f.flush()

            poly_geom_handler: PolyGeomHandler = PolyGeomHandler()
            poly_geom_handler.load_poly(f.name)

            # Inside area1 but outside hole1
            assert poly_geom_handler.is_in_poly(0.5, 0.5)

            # Inside the hole1
            assert not poly_geom_handler.is_in_poly(1.5, 1.5)

            # Inside area2
            assert poly_geom_handler.is_in_poly(4.5, 4.5)

            # Outside all
            assert not poly_geom_handler.is_in_poly(6, 6)
