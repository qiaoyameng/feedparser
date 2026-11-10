# Support for the GeoRSS format
# Copyright 2010-2025 Kurt McKee <contactme@kurtmckee.org>
# Copyright 2002-2008 Mark Pilgrim
# All rights reserved.
#
# This file is a part of feedparser.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#
# * Redistributions of source code must retain the above copyright notice,
#   this list of conditions and the following disclaimer.
# * Redistributions in binary form must reproduce the above copyright notice,
#   this list of conditions and the following disclaimer in the documentation
#   and/or other materials provided with the distribution.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS 'AS IS'
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
# ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT OWNER OR CONTRIBUTORS BE
# LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
# CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
# SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
# INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN
# CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
# ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
# POSSIBILITY OF SUCH DAMAGE.

import math
import re

from ..util import FeedParserDict


class Namespace:
    supported_namespaces = {
        "http://www.w3.org/2003/01/geo/wgs84_pos#": "geo",
        "http://www.georss.org/georss": "georss",
        "http://www.opengis.net/gml": "gml",
    }

    def __init__(self):
        self.ingeometry = 0
        # A stack of [depth, kind, srsName, srsDimension, context] lists
        # tracking the coordinate reference system declared by enclosing
        # elements. Kinds are "container" (georss:where), "geometry"
        # (gml:Point and friends), "ring" (gml:exterior and friends), and
        # "coord" (gml:pos and gml:posList).
        self._srs_scope_stack = []
        super().__init__()

    def _push_srs_scope(self, attrs_d, kind, keep_kinds):
        # Push a CRS scope for the current element, inheriting srsName and
        # srsDimension from enclosing elements unless locally overridden.
        # Scopes that cannot enclose the current element are discarded
        # first: scopes from another context (e.g. a previous entry),
        # scopes at unexpected depths, and scopes whose kind cannot be an
        # ancestor of this element. This keeps state from leaking between
        # geometry objects, even with unbalanced markup in loose parsing.
        context = self._get_context()
        depth = self.depth
        self._srs_scope_stack = [
            scope
            for scope in self._srs_scope_stack
            if scope[4] is context and scope[0] < depth and scope[1] in keep_kinds
        ]
        srs_name = attrs_d.get("srsname")
        srs_dimension = attrs_d.get("srsdimension")
        if self._srs_scope_stack:
            if srs_name is None:
                srs_name = self._srs_scope_stack[-1][2]
            if srs_dimension is None:
                srs_dimension = self._srs_scope_stack[-1][3]
        try:
            srs_dimension = int(srs_dimension)
        except (TypeError, ValueError):
            srs_dimension = 2
        self._srs_scope_stack.append([depth, kind, srs_name, srs_dimension, context])
        return srs_name, srs_dimension

    def _current_srs_scope(self):
        # Return the effective (srsName, srsDimension) for the current
        # element, discarding scopes left behind by other contexts or by
        # unbalanced elements.
        context = self._get_context()
        depth = self.depth
        self._srs_scope_stack = [
            scope
            for scope in self._srs_scope_stack
            if scope[4] is context and scope[0] <= depth
        ]
        if self._srs_scope_stack:
            return self._srs_scope_stack[-1][2], self._srs_scope_stack[-1][3]
        return None, 2

    def _record_where_srs(self, srs_name, srs_dimension):
        context = self._get_context()
        if "where" not in context:
            context["where"] = FeedParserDict()
        context["where"]["srsName"] = srs_name
        context["where"]["srsDimension"] = srs_dimension

    def _start_georssgeom(self, attrs_d):
        self.push("geometry", 0)
        # GeoRSS Simple geometries never carry a CRS declaration; discard
        # any scopes left behind by previous geometry elements.
        self._srs_scope_stack = []
        context = self._get_context()
        context["where"] = FeedParserDict()
        context.pop("normalized_geometry", None)

    _start_georss_point = _start_georssgeom
    _start_georss_line = _start_georssgeom
    _start_georss_polygon = _start_georssgeom
    _start_georss_box = _start_georssgeom

    def _save_where(self, geometry):
        context = self._get_context()
        where = context.setdefault("where", FeedParserDict())
        if geometry.get("type") == "Polygon" and where.get("type") == "Polygon":
            # Accumulate exterior/interior rings of a single GML polygon
            # instead of letting each ring overwrite the previous one.
            where["coordinates"] = tuple(where.get("coordinates") or ()) + tuple(
                geometry["coordinates"]
            )
        else:
            where.update(geometry)

    def _save_normalized_geometry(self, normalized):
        context = self._get_context()
        existing = context.get("normalized_geometry")
        if (
            existing is not None
            and existing.get("type") == "Polygon"
            and normalized.get("type") == "Polygon"
        ):
            if existing.get("error") is None and normalized.get("error") is None:
                # Merge exterior/interior rings of a single GML polygon.
                existing["coordinates"] = tuple(existing["coordinates"]) + tuple(
                    normalized["coordinates"]
                )
                return
            if existing.get("error") is not None:
                # Keep the first error encountered for this geometry.
                return
        context["normalized_geometry"] = normalized

    def _end_georss_point(self):
        this = self.pop("geometry")
        geometry = _parse_georss_point(this)
        if geometry:
            self._save_where(geometry)
        self._save_normalized_geometry(
            _normalize_geometry("Point", (this,), None, 2, simple=True)
        )

    def _end_georss_line(self):
        this = self.pop("geometry")
        geometry = _parse_georss_line(this)
        if geometry:
            self._save_where(geometry)
        self._save_normalized_geometry(
            _normalize_geometry("LineString", (this,), None, 2, simple=True)
        )

    def _end_georss_polygon(self):
        this = self.pop("geometry")
        geometry = _parse_georss_polygon(this)
        if geometry:
            self._save_where(geometry)
        self._save_normalized_geometry(
            _normalize_geometry("Polygon", (this,), None, 2, simple=True)
        )

    def _end_georss_box(self):
        this = self.pop("geometry")
        geometry = _parse_georss_box(this)
        if geometry:
            self._save_where(geometry)
        self._save_normalized_geometry(
            _normalize_geometry("Box", (this,), None, 2, simple=True)
        )

    def _start_where(self, attrs_d):
        self.push("where", 0)
        self._push_srs_scope(attrs_d, "container", ())
        context = self._get_context()
        context["where"] = FeedParserDict()
        context.pop("normalized_geometry", None)

    _start_georss_where = _start_where

    def _start_gml_point(self, attrs_d):
        srs_name, srs_dimension = self._push_srs_scope(
            attrs_d, "geometry", ("container",)
        )
        self._record_where_srs(srs_name, srs_dimension)
        self.ingeometry = 1
        self.push("geometry", 0)

    def _start_gml_linestring(self, attrs_d):
        srs_name, srs_dimension = self._push_srs_scope(
            attrs_d, "geometry", ("container",)
        )
        self._record_where_srs(srs_name, srs_dimension)
        self.ingeometry = "linestring"
        self.push("geometry", 0)

    def _start_gml_polygon(self, attrs_d):
        srs_name, srs_dimension = self._push_srs_scope(
            attrs_d, "geometry", ("container",)
        )
        # A new polygon starts a new geometry; previously parsed rings or
        # geometries must not leak into it.
        context = self._get_context()
        context["where"] = FeedParserDict()
        context.pop("normalized_geometry", None)
        self._record_where_srs(srs_name, srs_dimension)
        self.push("geometry", 0)

    def _start_gml_exterior(self, attrs_d):
        self._push_srs_scope(attrs_d, "ring", ("container", "geometry"))
        self.push("geometry", 0)

    def _start_gml_interior(self, attrs_d):
        self._push_srs_scope(attrs_d, "ring", ("container", "geometry"))
        self.push("geometry", 0)

    def _start_gml_linearring(self, attrs_d):
        self._push_srs_scope(attrs_d, "ring", ("container", "geometry"))
        self.ingeometry = "polygon"
        self.push("geometry", 0)

    def _start_gml_pos(self, attrs_d):
        self._push_srs_scope(attrs_d, "coord", ("container", "geometry", "ring"))
        self.push("pos", 0)

    def _end_gml_pos(self):
        this = self.pop("pos")
        srs_name, srs_dimension = self._current_srs_scope()
        swap = _legacy_axis_swap(srs_name)
        geometry = _parse_georss_point(this, swap=swap, dims=srs_dimension)
        if geometry:
            self._save_where(geometry)
        self._save_normalized_geometry(
            _normalize_geometry("Point", (this,), srs_name, srs_dimension, simple=False)
        )

    def _start_gml_poslist(self, attrs_d):
        self._push_srs_scope(attrs_d, "coord", ("container", "geometry", "ring"))
        self.push("pos", 0)

    def _end_gml_poslist(self):
        this = self.pop("pos")
        srs_name, srs_dimension = self._current_srs_scope()
        swap = _legacy_axis_swap(srs_name)
        geometry = _parse_poslist(this, self.ingeometry, swap=swap, dims=srs_dimension)
        if geometry:
            self._save_where(geometry)
        if self.ingeometry == "linestring":
            geom_type = "LineString"
        elif self.ingeometry == "polygon":
            geom_type = "Polygon"
        else:
            geom_type = None
        if geom_type is not None:
            self._save_normalized_geometry(
                _normalize_geometry(
                    geom_type, (this,), srs_name, srs_dimension, simple=False
                )
            )

    def _end_geom(self):
        self.ingeometry = 0
        self.pop("geometry")

    _end_gml_point = _end_geom
    _end_gml_linestring = _end_geom
    _end_gml_linearring = _end_geom
    _end_gml_exterior = _end_geom
    _end_gml_interior = _end_geom
    _end_gml_polygon = _end_geom

    def _end_where(self):
        self.pop("where")

    _end_georss_where = _end_where


def _legacy_axis_swap(srs_name):
    # Historical axis-order heuristic used for the legacy "where" result.
    swap = True
    if srs_name and "EPSG" in srs_name:
        try:
            epsg = int(srs_name.split(":")[-1])
        except ValueError:
            epsg = None
        swap = bool(epsg in _geogCS)
    return swap


# GeoRSS geometry parsers. Each return a dict with 'type' and 'coordinates'
# items, or None in the case of a parsing error.


def _parse_poslist(value, geom_type, swap=True, dims=2):
    if geom_type == "linestring":
        return _parse_georss_line(value, swap, dims)
    if geom_type == "polygon":
        ring = _parse_georss_line(value, swap, dims)
        return {"type": "Polygon", "coordinates": (ring["coordinates"],)}
    return None


def _gen_georss_coords(value, swap=True, dims=2):
    # A generator of (lon, lat) pairs from a string of encoded GeoRSS
    # coordinates. Converts to floats and swaps order.
    latlons = (float(ll) for ll in value.replace(",", " ").split())
    while True:
        try:
            t = [next(latlons), next(latlons)][:: swap and -1 or 1]
            if dims == 3:
                t.append(next(latlons))
            yield tuple(t)
        except StopIteration:
            return


def _parse_georss_point(value, swap=True, dims=2):
    # A point contains a single latitude-longitude pair, separated by
    # whitespace. We'll also handle comma separators.
    try:
        coords = list(_gen_georss_coords(value, swap, dims))
        return {"type": "Point", "coordinates": coords[0]}
    except (IndexError, ValueError):
        return None


def _parse_georss_line(value, swap=True, dims=2):
    # A line contains a space separated list of latitude-longitude pairs in
    # WGS84 coordinate reference system, with each pair separated by
    # whitespace. There must be at least two pairs.
    try:
        coords = list(_gen_georss_coords(value, swap, dims))
        return {"type": "LineString", "coordinates": coords}
    except (IndexError, ValueError):
        return None


def _parse_georss_polygon(value, swap=True, dims=2):
    # A polygon contains a space separated list of latitude-longitude pairs,
    # with each pair separated by whitespace. There must be at least four
    # pairs, with the last being identical to the first (so a polygon has a
    # minimum of three actual points).
    try:
        ring = list(_gen_georss_coords(value, swap, dims))
    except (IndexError, ValueError):
        return None
    if len(ring) < 4:
        return None
    return {"type": "Polygon", "coordinates": (ring,)}


def _parse_georss_box(value, swap=True, dims=2):
    # A bounding box is a rectangular region, often used to define the extents
    # of a map or a rough area of interest. A box contains two space separate
    # latitude-longitude pairs, with each pair separated by whitespace. The
    # first pair is the lower corner, the second is the upper corner.
    try:
        coords = list(_gen_georss_coords(value, swap, dims))
        return {"type": "Box", "coordinates": tuple(coords)}
    except (IndexError, ValueError):
        return None


# Normalized geometry support.
#
# The normalized geometry is an explicit longitude/latitude view of a
# GeoRSS geometry. It records the coordinate reference system the source
# coordinates were declared in, their axis order, and how (or whether)
# they were converted, so the two numbers in a geometry are never again
# mistaken for a raw latitude/longitude pair.

# The Earth radius used by EPSG:3857 (Web Mercator), in meters, and the
# maximum valid easting/northing value in that projection.
_WEB_MERCATOR_RADIUS = 6378137.0
_WEB_MERCATOR_LIMIT = math.pi * _WEB_MERCATOR_RADIUS

# The CRS that normalized coordinates are always expressed in.
_NORMALIZED_CRS = "OGC:CRS84"

# Human-readable descriptions of the transformation applied to source
# coordinates to produce the normalized longitude/latitude view.
_TRANSFORMATIONS = {
    "lat_lon": "axis-reorder",
    "lon_lat": "none",
    "easting_northing": "web-mercator-inverse",
}

_EPSG_PATTERN = re.compile(r"EPSG(?::[^:/]*)?:(\d+)$|EPSG(?:/[^/]*)?/(\d+)$")


def _identify_crs(srs_name):
    # Identify a declared srsName. Returns a (canonical name, axis order)
    # tuple for supported reference systems, or (None, None) for unknown
    # ones. Supported: EPSG:4326 (latitude, longitude), OGC:CRS84
    # (longitude, latitude), and EPSG:3857 (easting, northing in meters).
    text = srs_name.strip()
    if not text:
        return None, None
    if "CRS84" in text.upper():
        return "OGC:CRS84", "lon_lat"
    match = _EPSG_PATTERN.search(text)
    if match:
        code = match.group(1) or match.group(2)
        if code == "4326":
            return "EPSG:4326", "lat_lon"
        if code == "3857":
            return "EPSG:3857", "easting_northing"
    return None, None


def _inverse_web_mercator(x, y):
    # Convert EPSG:3857 easting/northing (meters) to WGS84 lon/lat.
    longitude = math.degrees(x / _WEB_MERCATOR_RADIUS)
    latitude = math.degrees(
        2.0 * math.atan(math.exp(y / _WEB_MERCATOR_RADIUS)) - math.pi / 2.0
    )
    return longitude, latitude


def _strict_coordinate_groups(value, dims):
    # Parse a coordinate string into groups of `dims` numbers. Unlike the
    # legacy parsers, incomplete trailing groups, non-numeric values, and
    # non-finite values are rejected instead of silently dropped.
    parts = value.replace(",", " ").split()
    if not parts:
        return None, "no-coordinates"
    numbers = []
    for part in parts:
        try:
            number = float(part)
        except ValueError:
            return None, "invalid-coordinate"
        if not math.isfinite(number):
            return None, "non-finite-coordinate"
        numbers.append(number)
    if len(numbers) % dims:
        return None, "incomplete-coordinate-group"
    groups = [tuple(numbers[i : i + dims]) for i in range(0, len(numbers), dims)]
    return groups, None


def _check_cardinality(geom_type, rings):
    if geom_type == "Point":
        if not rings or not rings[0]:
            return "insufficient-coordinates"
    elif geom_type == "LineString":
        if not rings or len(rings[0]) < 2:
            return "insufficient-coordinates"
    elif geom_type == "Polygon":
        if not rings or any(len(ring) < 4 for ring in rings):
            return "insufficient-coordinates"
    elif geom_type == "Box":
        if not rings or len(rings[0]) < 2:
            return "insufficient-coordinates"
    return None


def _convert_groups(groups, axis_order):
    # Convert raw coordinate groups to the (longitude, latitude[, ...])
    # view, preserving any additional dimensions (e.g. altitude).
    if axis_order == "lat_lon":
        return [(group[1], group[0]) + group[2:] for group in groups], None
    if axis_order == "lon_lat":
        return list(groups), None
    if axis_order == "easting_northing":
        converted = []
        for group in groups:
            x, y = group[0], group[1]
            if abs(x) > _WEB_MERCATOR_LIMIT or abs(y) > _WEB_MERCATOR_LIMIT:
                return None, "coordinate-out-of-range"
            longitude, latitude = _inverse_web_mercator(x, y)
            converted.append((longitude, latitude) + group[2:])
        return converted, None
    return None, "unsupported-crs"


def _shape_coordinates(geom_type, rings):
    if geom_type == "Point":
        return rings[0][0]
    if geom_type == "LineString":
        return list(rings[0])
    if geom_type == "Polygon":
        # Each ring stays a distinct coordinate list; exterior and interior
        # rings are never flattened into a single line.
        return tuple(list(ring) for ring in rings)
    if geom_type == "Box":
        return (rings[0][0], rings[0][1])
    return None


def _normalize_geometry(geom_type, texts, srs_name, srs_dimension, simple):
    # Build the normalized geometry result for a parsed geometry element.
    # `texts` holds the raw coordinate strings (one per polygon ring).
    if simple:
        # GeoRSS Simple coordinates are always WGS84 latitude/longitude.
        source_crs = "EPSG:4326"
        canonical, axis_order = "EPSG:4326", "lat_lon"
    elif srs_name:
        source_crs = srs_name
        canonical, axis_order = _identify_crs(srs_name)
    else:
        # The GeoRSS GML profile defaults to WGS84 latitude/longitude.
        source_crs = "EPSG:4326"
        canonical, axis_order = "EPSG:4326", "lat_lon"
    try:
        dims = int(srs_dimension)
    except (TypeError, ValueError):
        dims = 2
    normalized = FeedParserDict(
        {
            "type": geom_type,
            "coordinates": None,
            "crs": None,
            "source_crs": source_crs,
            "axis_order": axis_order or "unknown",
            "srs_dimension": dims,
            "converted": False,
            "transformation": None,
            "error": None,
        }
    )
    if dims not in (2, 3):
        normalized["error"] = "unsupported-dimension"
        return normalized
    if canonical is None:
        # The reference system is unknown, so the coordinates are
        # explicitly left unconverted.
        normalized["error"] = "unsupported-crs"
        return normalized
    rings = []
    for text in texts:
        groups, error = _strict_coordinate_groups(text, dims)
        if error is not None:
            normalized["error"] = error
            return normalized
        rings.append(groups)
    error = _check_cardinality(geom_type, rings)
    if error is not None:
        normalized["error"] = error
        return normalized
    converted_rings = []
    for groups in rings:
        converted, error = _convert_groups(groups, axis_order)
        if error is not None:
            normalized["error"] = error
            return normalized
        converted_rings.append(converted)
    normalized["coordinates"] = _shape_coordinates(geom_type, converted_rings)
    normalized["crs"] = _NORMALIZED_CRS
    normalized["converted"] = True
    normalized["transformation"] = _TRANSFORMATIONS[axis_order]
    return normalized


# The list of EPSG codes for geographic (latitude/longitude) coordinate
# systems to support decoding of GeoRSS GML profiles.
_geogCS = [
    3819,
    3821,
    3824,
    3889,
    3906,
    4001,
    4002,
    4003,
    4004,
    4005,
    4006,
    4007,
    4008,
    4009,
    4010,
    4011,
    4012,
    4013,
    4014,
    4015,
    4016,
    4018,
    4019,
    4020,
    4021,
    4022,
    4023,
    4024,
    4025,
    4027,
    4028,
    4029,
    4030,
    4031,
    4032,
    4033,
    4034,
    4035,
    4036,
    4041,
    4042,
    4043,
    4044,
    4045,
    4046,
    4047,
    4052,
    4053,
    4054,
    4055,
    4075,
    4081,
    4120,
    4121,
    4122,
    4123,
    4124,
    4125,
    4126,
    4127,
    4128,
    4129,
    4130,
    4131,
    4132,
    4133,
    4134,
    4135,
    4136,
    4137,
    4138,
    4139,
    4140,
    4141,
    4142,
    4143,
    4144,
    4145,
    4146,
    4147,
    4148,
    4149,
    4150,
    4151,
    4152,
    4153,
    4154,
    4155,
    4156,
    4157,
    4158,
    4159,
    4160,
    4161,
    4162,
    4163,
    4164,
    4165,
    4166,
    4167,
    4168,
    4169,
    4170,
    4171,
    4172,
    4173,
    4174,
    4175,
    4176,
    4178,
    4179,
    4180,
    4181,
    4182,
    4183,
    4184,
    4185,
    4188,
    4189,
    4190,
    4191,
    4192,
    4193,
    4194,
    4195,
    4196,
    4197,
    4198,
    4199,
    4200,
    4201,
    4202,
    4203,
    4204,
    4205,
    4206,
    4207,
    4208,
    4209,
    4210,
    4211,
    4212,
    4213,
    4214,
    4215,
    4216,
    4218,
    4219,
    4220,
    4221,
    4222,
    4223,
    4224,
    4225,
    4226,
    4227,
    4228,
    4229,
    4230,
    4231,
    4232,
    4233,
    4234,
    4235,
    4236,
    4237,
    4238,
    4239,
    4240,
    4241,
    4242,
    4243,
    4244,
    4245,
    4246,
    4247,
    4248,
    4249,
    4250,
    4251,
    4252,
    4253,
    4254,
    4255,
    4256,
    4257,
    4258,
    4259,
    4260,
    4261,
    4262,
    4263,
    4264,
    4265,
    4266,
    4267,
    4268,
    4269,
    4270,
    4271,
    4272,
    4273,
    4274,
    4275,
    4276,
    4277,
    4278,
    4279,
    4280,
    4281,
    4282,
    4283,
    4284,
    4285,
    4286,
    4287,
    4288,
    4289,
    4291,
    4292,
    4293,
    4294,
    4295,
    4296,
    4297,
    4298,
    4299,
    4300,
    4301,
    4302,
    4303,
    4304,
    4306,
    4307,
    4308,
    4309,
    4310,
    4311,
    4312,
    4313,
    4314,
    4315,
    4316,
    4317,
    4318,
    4319,
    4322,
    4324,
    4326,
    4463,
    4470,
    4475,
    4483,
    4490,
    4555,
    4558,
    4600,
    4601,
    4602,
    4603,
    4604,
    4605,
    4606,
    4607,
    4608,
    4609,
    4610,
    4611,
    4612,
    4613,
    4614,
    4615,
    4616,
    4617,
    4618,
    4619,
    4620,
    4621,
    4622,
    4623,
    4624,
    4625,
    4626,
    4627,
    4628,
    4629,
    4630,
    4631,
    4632,
    4633,
    4634,
    4635,
    4636,
    4637,
    4638,
    4639,
    4640,
    4641,
    4642,
    4643,
    4644,
    4645,
    4646,
    4657,
    4658,
    4659,
    4660,
    4661,
    4662,
    4663,
    4664,
    4665,
    4666,
    4667,
    4668,
    4669,
    4670,
    4671,
    4672,
    4673,
    4674,
    4675,
    4676,
    4677,
    4678,
    4679,
    4680,
    4681,
    4682,
    4683,
    4684,
    4685,
    4686,
    4687,
    4688,
    4689,
    4690,
    4691,
    4692,
    4693,
    4694,
    4695,
    4696,
    4697,
    4698,
    4699,
    4700,
    4701,
    4702,
    4703,
    4704,
    4705,
    4706,
    4707,
    4708,
    4709,
    4710,
    4711,
    4712,
    4713,
    4714,
    4715,
    4716,
    4717,
    4718,
    4719,
    4720,
    4721,
    4722,
    4723,
    4724,
    4725,
    4726,
    4727,
    4728,
    4729,
    4730,
    4731,
    4732,
    4733,
    4734,
    4735,
    4736,
    4737,
    4738,
    4739,
    4740,
    4741,
    4742,
    4743,
    4744,
    4745,
    4746,
    4747,
    4748,
    4749,
    4750,
    4751,
    4752,
    4753,
    4754,
    4755,
    4756,
    4757,
    4758,
    4759,
    4760,
    4761,
    4762,
    4763,
    4764,
    4765,
    4801,
    4802,
    4803,
    4804,
    4805,
    4806,
    4807,
    4808,
    4809,
    4810,
    4811,
    4813,
    4814,
    4815,
    4816,
    4817,
    4818,
    4819,
    4820,
    4821,
    4823,
    4824,
    4901,
    4902,
    4903,
    4904,
    4979,
]
