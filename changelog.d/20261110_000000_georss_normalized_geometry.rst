Added
-----

*   Added an explicit ``normalized_geometry`` result for GeoRSS geometries.

    Each parsed geometry now also produces a ``normalized_geometry`` mapping
    with a uniform longitude/latitude view of point, line, polygon, and box
    geometries, alongside the unchanged legacy ``where`` result. It records
    the source coordinate reference system, the source axis order, and how
    (or whether) the coordinates were converted. GeoRSS Simple (WGS84),
    EPSG:4326, OGC:CRS84, and EPSG:3857 are supported; ``srsName`` and
    ``srsDimension`` are inherited through element scope and can be overridden
    locally. EPSG:3857 coordinates are inverse-projected to WGS84, third
    dimensions are preserved, and incomplete coordinate groups, non-finite
    values, and out-of-range projected coordinates are rejected. Unknown
    reference systems are explicitly reported as not converted. GML polygon
    exterior and interior rings are kept as distinct rings.
