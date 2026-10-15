"""Reconstruct exact layout georeferencing and audit the saved SAM labels."""
from pathlib import Path
import json
import zipfile
import xml.etree.ElementTree as ET

import numpy as np
import rasterio
from affine import Affine
from rasterio.features import shapes
import geopandas as gpd
from shapely.geometry import shape
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parent
OUT = ROOT / 'output'

def load_corrected():
    with zipfile.ZipFile(ROOT / 'Visible_Esri_SamGeo_Test.qgz') as archive:
        root = ET.fromstring(archive.read(next(n for n in archive.namelist() if n.endswith('.qgs'))))
    item = next(x for x in root.findall('.//Layouts/Layout/LayoutItem') if x.get('type') == '65639')
    extent = {k: float(v) for k, v in item.find('Extent').attrib.items()}
    dpi = 300
    x_mm, y_mm = map(float, item.get('position').split(',')[:2])
    w_mm, h_mm = map(float, item.get('size').split(',')[:2])
    # Previous crop was (141, 282, 2801, 1728) in the 300-dpi layout PNG.
    sx = (extent['xmax'] - extent['xmin']) / (w_mm * dpi / 25.4)
    sy = (extent['ymax'] - extent['ymin']) / (h_mm * dpi / 25.4)
    transform = Affine(sx, 0, extent['xmin'] + (141-x_mm*dpi/25.4)*sx,
                       0, -sy, extent['ymax'] - (282-y_mm*dpi/25.4)*sy)
    with rasterio.open(ROOT / 'data/visible_esri_test.tif') as src:
        rgb = src.read()
        profile = src.profile.copy()
        old_bounds = list(src.bounds)
    profile.update(transform=transform)
    with rasterio.open(ROOT / 'data/esri_test_aligned.tif', 'w', **profile) as dst:
        dst.write(rgb)
        dst.update_tags(source='Esri World Imagery', georeferencing='QGIS layout map extent and DPI; original crop offsets')
    with rasterio.open(OUT / 'visible_esri_sam_masks.tif') as src:
        labels = src.read(1)
        mask_profile = src.profile.copy()
    mask_profile.update(transform=transform)
    with rasterio.open(OUT / 'sam_masks_aligned.tif', 'w', **mask_profile) as dst:
        dst.write(labels, 1)
    report = {'previous_bounds': old_bounds, 'layout_extent': extent,
              'corrected_transform': list(transform), 'shape': list(labels.shape),
              'label_count': int(np.unique(labels[labels>0]).size)}
    return rgb, labels, transform, profile, report

def main():
    rgb, labels, transform, profile, report = load_corrected()
    rows = []
    for geom, value in shapes(labels.astype('int32'), mask=labels>0, transform=transform):
        rows.append({'sam_id': int(value), 'geometry': shape(geom)})
    gpd.GeoDataFrame(rows, crs=profile['crs']).to_file(OUT/'sam_segments_aligned.gpkg', layer='segments', driver='GPKG')
    stats=[]
    fig, ax=plt.subplots(figsize=(16,9))
    ax.imshow(np.moveaxis(rgb,0,2))
    from skimage.segmentation import find_boundaries
    boundaries=find_boundaries(labels, mode='inner')
    overlay=np.zeros((*labels.shape,4)); overlay[boundaries]=[1,0,1,0.85]
    ax.imshow(overlay)
    for value in np.unique(labels):
        if value==0: continue
        yy,xx=np.where(labels==value)
        mean=rgb[:,yy,xx].mean(axis=1)
        stats.append({'id':int(value),'pixels':len(xx),'rgb':mean.round(1).tolist()})
        if len(xx)>4000:
            ax.text(float(np.median(xx)),float(np.median(yy)),str(value),fontsize=7,color='white',bbox=dict(facecolor='black',alpha=.6,pad=1))
    ax.axis('off'); fig.tight_layout(); fig.savefig(OUT/'aligned_sam_audit.png',dpi=140); plt.close(fig)
    report['segments']=stats
    (OUT/'alignment_audit.json').write_text(json.dumps(report,indent=2))
    print(json.dumps(report,indent=2))

if __name__=='__main__': main()
