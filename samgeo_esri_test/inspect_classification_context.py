from pathlib import Path
import rasterio
import geopandas as gpd
from shapely.geometry import box
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT=Path(__file__).resolve().parent
OUT=ROOT/'output/full_classification'
OUT.mkdir(exist_ok=True)
with rasterio.open(ROOT/'data/esri_test_aligned.tif') as src:
    rgb=src.read().transpose(1,2,0); t=src.transform; crs=src.crs; bounds=src.bounds
roads_path=ROOT.parent/'Codes/data/processed/Bhadra/osm/bhadra_osm_context.gpkg'
roads=gpd.read_file(roads_path,layer='roads').to_crs(crs)
roads=roads[roads.intersects(box(*bounds))].copy()
roads.geometry=roads.geometry.intersection(box(*bounds))
roads.to_file(OUT/'context.gpkg',layer='osm_roads',driver='GPKG')
print(roads[['highway','name']].to_string(index=False))
fig,ax=plt.subplots(figsize=(19,11))
ax.imshow(rgb,extent=(bounds.left,bounds.right,bounds.bottom,bounds.top))
roads.plot(ax=ax,color='#ff00ff',linewidth=1)
ax.set_xlim(bounds.left,bounds.right); ax.set_ylim(bounds.bottom,bounds.top)
ax.set_xticks([t*(i,0) for i in []])
ax.set_axis_off(); fig.tight_layout()
fig.savefig(OUT/'road_context_audit.png',dpi=140); plt.close(fig)
fig,ax=plt.subplots(figsize=(20,11))
ax.imshow(rgb); ax.set_xticks(range(0,2660,200)); ax.set_yticks(range(0,1446,200)); ax.grid(alpha=.5)
fig.tight_layout(); fig.savefig(OUT/'source_pixel_grid.png',dpi=140); plt.close(fig)
