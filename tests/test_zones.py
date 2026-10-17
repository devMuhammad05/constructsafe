import pytest

from constructsafe.zones import (
    DangerZone,
    ZoneConfigError,
    load_zones,
    parse_zone_arg,
    point_in_polygon,
    save_zones,
    zones_for_source,
)

SQUARE = ((0.2, 0.2), (0.6, 0.2), (0.6, 0.6), (0.2, 0.6))
# L-shape: concave, to check ray casting beyond convex polygons
L_SHAPE = ((0.0, 0.0), (0.5, 0.0), (0.5, 0.5), (1.0, 0.5), (1.0, 1.0), (0.0, 1.0))


@pytest.mark.parametrize(
    "point, expected",
    [
        ((0.4, 0.4), True),  # centre
        ((0.1, 0.4), False),  # left
        ((0.7, 0.4), False),  # right
        ((0.4, 0.9), False),  # below
        ((0.2, 0.4), True),  # on left edge: boundary counts as inside
        ((0.6, 0.6), True),  # on a vertex
    ],
)
def test_point_in_square(point, expected):
    assert point_in_polygon(point, SQUARE) is expected


def test_point_in_concave_polygon():
    assert point_in_polygon((0.25, 0.25), L_SHAPE)
    assert point_in_polygon((0.75, 0.75), L_SHAPE)
    assert not point_in_polygon((0.75, 0.25), L_SHAPE)  # the notch


def test_degenerate_polygon_contains_nothing():
    assert not point_in_polygon((0.0, 0.0), ((0.0, 0.0), (1.0, 1.0)))


def test_contains_pixel_is_resolution_independent():
    zone = DangerZone("z", "Z", SQUARE)
    assert zone.contains_pixel((400, 300), 1000, 750)  # (0.4, 0.4)
    assert zone.contains_pixel((200, 150), 500, 375)  # same point, half resolution
    assert not zone.contains_pixel((50, 300), 1000, 750)
    assert not zone.contains_pixel((1, 1), 0, 0)


def test_from_pixels_and_pixel_polygon_round_trip():
    zone = DangerZone.from_pixels("z", [(100, 50), (300, 50), (300, 150)], 400, 200)
    assert zone.polygon == ((0.25, 0.25), (0.75, 0.25), (0.75, 0.75))
    assert zone.pixel_polygon(400, 200) == [(100, 50), (300, 50), (300, 150)]


def test_zone_validation():
    with pytest.raises(ZoneConfigError, match="at least 3"):
        DangerZone("z", "Z", ((0.1, 0.1), (0.2, 0.2)))
    with pytest.raises(ZoneConfigError, match="outside"):
        DangerZone("z", "Z", ((0.1, 0.1), (1.5, 0.2), (0.2, 0.3)))


def test_parse_zone_arg():
    zone = parse_zone_arg("0.1,0.1; 0.9,0.1; 0.5,0.9", zone_id="excavator")
    assert zone.zone_id == "excavator"
    assert zone.polygon == ((0.1, 0.1), (0.9, 0.1), (0.5, 0.9))
    with pytest.raises(ZoneConfigError):
        parse_zone_arg("0.1;0.2")


def test_save_and_load_round_trip(tmp_path):
    zones = [
        DangerZone("excavator", "Excavator swing area", SQUARE, source_name="site.mp4"),
        DangerZone("truck", "Truck lane", L_SHAPE),
    ]
    path = tmp_path / "zones.json"
    save_zones(path, zones)
    assert load_zones(path) == zones


def test_load_rejects_bad_files(tmp_path):
    bad_json = tmp_path / "bad.json"
    bad_json.write_text("{not json")
    with pytest.raises(ZoneConfigError):
        load_zones(bad_json)

    empty = tmp_path / "empty.json"
    empty.write_text('{"zones": []}')
    with pytest.raises(ZoneConfigError, match="no zones"):
        load_zones(empty)

    missing_polygon = tmp_path / "missing.json"
    missing_polygon.write_text('{"zones": [{"zone_id": "a"}]}')
    with pytest.raises(ZoneConfigError):
        load_zones(missing_polygon)

    dupes = tmp_path / "dupes.json"
    dupes.write_text(
        '{"zones": [{"zone_id": "a", "polygon": [[0,0],[1,0],[1,1]]},'
        ' {"zone_id": "a", "polygon": [[0,0],[1,0],[1,1]]}]}'
    )
    with pytest.raises(ZoneConfigError, match="duplicate"):
        load_zones(dupes)


def test_zones_for_source():
    a = DangerZone("a", "A", SQUARE, source_name="site.mp4")
    b = DangerZone("b", "B", SQUARE, source_name="other.mp4")
    c = DangerZone("c", "C", SQUARE)
    assert zones_for_source([a, b, c], "site.mp4") == [a, c]
