"""Point/box-prompted SamGeo on the industrial crop; no manual output shapes.

Prompt coordinates use the existing audit image coordinate frame. Semantic
types are visual interpretations, not learned classes or verified facility use.
"""
from pathlib import Path
import json
import sys
import numpy as np
import rasterio
from rasterio.features import shapes
from rasterio.windows import Window
from shapely.geometry import shape
import geopandas as gpd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from skimage.segmentation import find_boundaries

ROOT=Path(__file__).resolve().parent
OUT=ROOT/'output'
JOBS={
 'tank_west':('Circular tank / treatment unit',(860,780),(826,743,901,815)),
 'tank_south':('Circular tank / treatment unit',(955,882),(919,844,991,917)),
 'tank_east':('Circular tank / treatment unit',(1029,852),(991,817,1071,895)),
 'roof_northwest':('Roofed building',(839,571),(816,552,863,594)),
 'roof_north':('Roofed building',(953,567),(938,555,970,576)),
 'roof_northeast':('Roofed building',(966,579),(952,567,980,593)),
 'roof_central':('Roofed building',(956,678),(947,665,967,692)),
 'roof_small':('Roofed building',(929,675),(918,669,937,683)),
 'process_rectangular':('Rectangular process structure',(994,711),(977,693,1010,729)),
 'process_pad':('Rectangular process structure',(984,758),(955,732,1015,782)),
}

def source_point(x,y): return np.array([(x-20)*2660/2005,(y-30)*1446/1090])

def main():
    start=np.floor(source_point(730,540)).astype(int)
    end=np.ceil(source_point(1140,960)).astype(int)
    window=Window(start[0],start[1],*(end-start))
    with rasterio.open(ROOT/'data/esri_test_aligned.tif') as src:
        rgb=src.read(window=window).transpose(1,2,0)
        transform=src.window_transform(window); crs=src.crs
    reuse='--reuse-masks' in sys.argv
    if reuse:
        saved_masks=np.load(OUT/'industrial_prompt_masks.npz')
        saved=gpd.read_file(OUT/'industrial_candidates.gpkg',layer='candidates').set_index('object_id')
    else:
        import torch
        from samgeo import SamGeo
        torch.set_num_threads(4)
        print('Loading SAM ViT-H for industrial crop',flush=True)
        sam=SamGeo(model_type='vit_h',checkpoint=str(ROOT.parent/'samgeo/weights/sam_vit_h_4b8939.pth'),automatic=False,device='cpu')
        print('Encoding crop',rgb.shape,flush=True)
        sam.set_image(rgb)
    rows=[]; masks={}; audit={}
    fig,axs=plt.subplots(1,2,figsize=(14,8))
    for ax in axs: ax.imshow(rgb); ax.set_axis_off()
    axs[0].set_title('Esri industrial crop')
    axs[1].set_title('SAM candidates — review before inclusion')
    for name,(kind,center,bounds) in JOBS.items():
        xy=source_point(*center)-start
        x0,y0,x1,y1=bounds
        bbox=np.r_[source_point(x0,y0)-start,source_point(x1,y1)-start]
        if reuse:
            result=saved_masks[name][None,:,:]; scores=[saved.loc[name,'sam_score']]
        else:
            with torch.inference_mode():
                result,scores,_=sam.predictor.predict(point_coords=xy[None,:],point_labels=np.array([1]),box=bbox,multimask_output=False)
        mask=result[0]
        # Keep only the connected component selected by the positive point.
        from scipy import ndimage as ndi
        components,_=ndi.label(mask)
        idx=components[int(xy[1]),int(xy[0])]
        if idx==0: raise ValueError(f'{name}: positive prompt not in mask')
        mask=components==idx
        masks[name]=mask
        parts=[shape(g) for g,v in shapes(mask.astype('uint8'),mask=mask,transform=transform) if v==1]
        from shapely.ops import unary_union
        geometry=unary_union(parts)
        rows.append({'object_id':name,'class_id':5,'class_name':'Buildings / industrial structures',
            'subtype':kind,'sam_score':float(scores[0]),'method':'Point + box prompted SAM ViT-H',
            'review':'Candidate; visual review required','area_m2':geometry.area,'geometry':geometry})
        overlay=np.zeros((*mask.shape,4)); overlay[mask]=[1,.1,.15,.17]
        overlay[find_boundaries(mask,mode='inner')]=[1,.1,.15,1]
        axs[1].imshow(overlay)
        axs[1].text(xy[0],xy[1],name,fontsize=6,color='white',ha='center',bbox=dict(facecolor='black',alpha=.6,pad=1))
        audit[name]={'subtype':kind,'positive_audit':center,'box_audit':bounds,'sam_score_not_class_probability':float(scores[0]),'pixels':int(mask.sum()),'area_m2':geometry.area}
        print(name,int(mask.sum()),float(scores[0]),flush=True)
    gpd.GeoDataFrame(rows,crs=crs).to_file(OUT/'industrial_candidates.gpkg',layer='candidates',driver='GPKG')
    np.savez_compressed(OUT/'industrial_prompt_masks.npz',**masks)
    (OUT/'industrial_prompts.json').write_text(json.dumps({'crop_window':[int(v) for v in window.flatten()],'objects':audit},indent=2))
    fig.tight_layout(); fig.savefig(OUT/'industrial_candidates_preview.png',dpi=150)

if __name__=='__main__': main()
