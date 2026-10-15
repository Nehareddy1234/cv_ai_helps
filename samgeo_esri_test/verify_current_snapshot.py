"""Read-only verification of the portable current QGIS snapshot."""
from pathlib import Path
import hashlib
import json
import zipfile
import xml.etree.ElementTree as ET
import geopandas as gpd
import numpy as np
import rasterio
from rasterio.features import rasterize

ROOT = Path(__file__).resolve().parent
OUT = ROOT / 'output/combined_classes_with_uncertain'

def main():
    project = ROOT / 'Bhadra_Esri_SAM_ViT_H_Current.qgz'
    with zipfile.ZipFile(project) as archive:
        entries = [n for n in archive.namelist() if n.endswith('.qgs')]
        assert len(entries) == 1
        document = ET.fromstring(archive.read(entries[0]))
    layers = document.findall('./projectlayers/maplayer')
    assert len(layers) == 2, 'Only current result and Esri should remain'
    vectors = [l for l in layers if l.findtext('provider') == 'ogr']
    assert len(vectors) == 1
    source = vectors[0].findtext('datasource')
    assert source == './output/combined_classes_with_uncertain/combined_classes.gpkg|layername=combined_classes'
    assert (ROOT / source.split('|')[0]).is_file()
    assert any('World_Imagery' in l.findtext('datasource', '') for l in layers)
    categories = vectors[0].findall('./renderer-v2/categories/category')
    assert {int(c.attrib['value']) for c in categories} == {1, 3, 4}

    report = json.loads((OUT / 'verification.json').read_text())
    original_path = ROOT / 'output/full_classification/classified_regions.gpkg'
    assert hashlib.sha256(original_path.read_bytes()).hexdigest() == report['source_sha256']
    original = gpd.read_file(original_path, layer='classified_regions')
    grouped = gpd.read_file(OUT / 'combined_classes.gpkg', layer='reclassified_regions')
    merged = gpd.read_file(OUT / 'combined_classes.gpkg', layer='combined_classes')
    assert len(grouped) == len(original) == 2634
    assert len(merged) == 3 and set(merged.class_id) == {1, 3, 4}
    assert grouped.is_valid.all() and merged.is_valid.all()
    original = original.sort_values('segment_id').reset_index(drop=True)
    grouped = grouped.sort_values('segment_id').reset_index(drop=True)
    assert np.array_equal(original.segment_id, grouped.segment_id)
    assert np.array_equal(original.class_id, grouped.source_class_id)
    assert all(a.equals_exact(b, 0) for a, b in zip(original.geometry, grouped.geometry))
    expected = original.class_id.where(~original.class_id.isin({1, 2, 5, 6, 7, 8}), 1)
    assert np.array_equal(expected, grouped.class_id)
    assert int((grouped.class_id == 1).sum()) == 2176
    for row in merged.itertuples():
        union = grouped[grouped.class_id == row.class_id].geometry.union_all()
        assert union.symmetric_difference(row.geometry).area < .01
    union = merged.geometry.union_all()
    assert abs(merged.area.sum() - union.area) < .01
    with rasterio.open(OUT / 'combined_classes.tif') as src:
        pixels = src.read(1)
        assert src.crs == merged.crs
        rebuilt = rasterize(list(zip(merged.geometry, merged.class_id)),
                            out_shape=pixels.shape, transform=src.transform, dtype='uint8')
    assert np.array_equal(rebuilt, pixels)
    assert report['passed'] and report['merged_source_region_count'] == 2176
    print(json.dumps({'passed': True, 'project_layers': 2, 'categories': 3,
                      'combined_source_regions': 2176, 'all_source_regions': 2634,
                      'relative_source_resolves': True, 'vector_raster_identical': True}))

if __name__ == '__main__':
    main()
