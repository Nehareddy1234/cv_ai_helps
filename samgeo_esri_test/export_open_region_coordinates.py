"""Export class-4 open-ground polygons and WGS84 location coordinates."""
from pathlib import Path
import hashlib
import json
import geopandas as gpd

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / 'output/combined_classes_with_uncertain/combined_classes.gpkg'
OUT = ROOT / 'output/open_region_coordinates'

def main():
    before = hashlib.sha256(SOURCE.read_bytes()).hexdigest()
    regions = gpd.read_file(SOURCE, layer='reclassified_regions')
    regions = regions.loc[regions.class_id == 4].sort_values('segment_id').copy()
    assert len(regions) == 335 and regions.segment_id.is_unique
    assert regions.crs.to_epsg() == 32643 and regions.is_valid.all()
    centroids = regions.geometry.centroid
    interior = regions.geometry.representative_point()
    assert all(g.covers(p) for g, p in zip(regions.geometry, interior))
    centres_wgs = centroids.to_crs(4326)
    interior_wgs = interior.to_crs(4326)
    headers = ['segment_id', 'area_m2', 'centroid_latitude', 'centroid_longitude',
               'centroid_inside_region', 'interior_latitude', 'interior_longitude']
    records = []
    for i, region in regions.iterrows():
        records.append([int(region.segment_id), float(region.geometry.area),
                        float(centres_wgs.loc[i].y), float(centres_wgs.loc[i].x),
                        bool(region.geometry.covers(centroids.loc[i])),
                        float(interior_wgs.loc[i].y), float(interior_wgs.loc[i].x)])
    OUT.mkdir(exist_ok=True)
    data = {'headers': headers, 'rows': records, 'crs': 'EPSG:4326',
            'source': 'combined_classes_with_uncertain/combined_classes.gpkg; reclassified_regions; class_id=4',
            'class_name': 'Bare soil / rock / sparse ground',
            'area_crs': 'EPSG:32643', 'source_sha256': before}
    (OUT / 'coordinate_data.json').write_text(json.dumps(data, indent=2))
    polygons = regions[['segment_id', 'class_name', 'geometry']].copy()
    polygons['area_m2'] = regions.geometry.area
    polygons = polygons.to_crs(4326)
    polygons.to_file(OUT / 'open_region_boundaries.geojson', driver='GeoJSON', RFC7946='YES')
    saved = gpd.read_file(OUT / 'open_region_boundaries.geojson').to_crs(32643)
    assert list(saved.segment_id) == list(regions.segment_id)
    max_difference = max(a.hausdorff_distance(b) for a, b in zip(saved.geometry, regions.geometry))
    assert max_difference < .05
    assert all(13 < row[2] < 14 and 75 < row[3] < 76 for row in records)
    assert hashlib.sha256(SOURCE.read_bytes()).hexdigest() == before
    report = {'passed': True, 'regions': len(regions),
              'total_area_m2': float(regions.geometry.area.sum()),
              'centroids_outside_region': sum(not r[4] for r in records),
              'interior_points_all_inside': True, 'source_unchanged': True,
              'maximum_geojson_roundtrip_error_m': max_difference}
    (OUT / 'verification.json').write_text(json.dumps(report, indent=2))
    (OUT / 'README.md').write_text(
        '# Open-region coordinates\n\n'
        'All 335 original regions labelled Bare soil / rock / sparse ground (class 4). '
        'Crops/grass and uncertain regions are not included. These labels do not establish '
        'that land is vacant, accessible, safe or available for use.\n\n'
        'The table gives WGS84 / EPSG:4326 decimal degrees. Latitude and longitude '
        'have separate named columns. Centroids were computed in EPSG:32643 before '
        'transformation. Interior coordinates locate a point inside each patch; '
        'centroids can fall outside irregular polygons. Areas are square metres '
        'computed in EPSG:32643. Decimal precision is not surveyed accuracy.\n\n'
        'The GeoJSON contains full polygon boundaries, including holes, using '
        '[longitude, latitude] coordinate order. Match segment_id across files. '
        'No boundaries or source classifications were changed.\n')
    print(json.dumps(report, indent=2))
    print(json.dumps({'first_regions': records[:3]}))

if __name__ == '__main__':
    main()
