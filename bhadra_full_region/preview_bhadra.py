"""Render the input extent and, when available, the actual classified raster."""
from pathlib import Path
import numpy as np
import geopandas as gpd
import rasterio
from rasterio.enums import Resampling
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Patch

ROOT=Path(__file__).resolve().parent
OUT=ROOT/'output'; OUT.mkdir(exist_ok=True)
with rasterio.open(ROOT/'data/esri_world_imagery.tif') as src:
    h=1400; w=round(src.width*h/src.height)
    rgb=src.read(out_shape=(3,h,w),resampling=Resampling.average).transpose(1,2,0)
    b=src.bounds; extent=[b.left,b.right,b.bottom,b.top]; crs=src.crs
aoi=gpd.read_file(ROOT/'data/bhadra_boundary.geojson').to_crs(crs)
classified=OUT/'classified_regions.tif'
fig,ax=plt.subplots(figsize=(10,14))
ax.imshow(rgb,extent=extent)
if classified.exists():
    with rasterio.open(classified) as src:
        labels=src.read(1,out_shape=(h,w),resampling=Resampling.nearest)
    colors={1:('#2489ef','Water'),2:('#238443','Woody vegetation'),3:('#a4d65e','Low vegetation'),
            4:('#c88c47','Bare ground / rock'),8:('#9c9c9c','Uncertain')}
    overlay=np.zeros((h,w,4),'float32')
    for code,(color,name) in colors.items():
        overlay[labels==code]=[*matplotlib.colors.to_rgb(color),.55]
    ax.imshow(overlay,extent=extent)
    ax.legend(handles=[Patch(color=c,label=n) for c,n in colors.values()],loc='lower left')
aoi.boundary.plot(ax=ax,color='white',linewidth=.8)
ax.set_axis_off()
ax.set_title('Whole saved Bhadra AOI — Esri / SAM ViT-H' if classified.exists() else 'Whole saved Bhadra AOI — Esri source',fontsize=13)
fig.text(.5,.02,'Broad land-cover interpretation at ~19 m source sampling; not field-validated',ha='center',fontsize=10)
fig.tight_layout(rect=(0,.035,1,1))
target=OUT/('classification_overview.png' if classified.exists() else 'source_overview.png')
fig.savefig(target,dpi=115); plt.close(fig)
print(target)
