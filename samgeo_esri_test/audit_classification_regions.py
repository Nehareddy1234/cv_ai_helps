from pathlib import Path
import geopandas as gpd
import rasterio
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from shapely.geometry import box
ROOT=Path(__file__).resolve().parent
OUT=ROOT/'output/full_classification'
p=gpd.read_file(OUT/'classified_regions.gpkg',layer='classified_regions')
with rasterio.open(ROOT/'data/esri_test_aligned.tif') as s:
    rgb=s.read().transpose(1,2,0); t=s.transform; bounds=s.bounds
for name,(x0,x1,y0,y1) in {'dam':(0,900,600,1440),'bridge':(880,1380,0,760),
                           'plant':(950,1580,720,1445),'east':(1550,2658,100,1400)}.items():
    ax0,ay0=t*(x0,y1); ax1,ay1=t*(x1,y0); region=box(ax0,ay0,ax1,ay1)
    q=p[p.intersects(region)&(p.area_m2>130)&(p.origin!='Preserved footprint')]
    fig,ax=plt.subplots(figsize=(13,12)); ax.imshow(rgb,extent=(bounds.left,bounds.right,bounds.bottom,bounds.top))
    q.boundary.plot(ax=ax,color='#ffe57f',linewidth=.7)
    for row in q.itertuples():
        point=row.geometry.intersection(region).representative_point()
        ax.text(point.x,point.y,str(row.segment_id),fontsize=8,color='white',ha='center',
            bbox={'facecolor':'black','alpha':.65,'pad':1,'edgecolor':'none'})
    ax.set_xlim(ax0,ax1); ax.set_ylim(ay0,ay1); ax.set_axis_off(); ax.set_title(name+' — segment IDs')
    fig.tight_layout(); fig.savefig(OUT/f'audit_ids_{name}.png',dpi=140); plt.close(fig)
print(p[(p.class_id==8)&(p.area_m2>1500)][['segment_id','suggested_class','area_m2','model_score','vote_fraction','review_reason']].to_string(index=False))
