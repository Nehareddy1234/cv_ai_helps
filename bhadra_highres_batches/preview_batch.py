"""Show actual batch imagery and classification; never synthetic map artwork."""
import argparse
import numpy as np
import geopandas as gpd
import rasterio
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Patch
from skimage.segmentation import find_boundaries
from common import *

def preview(batch_id,combined=True):
    folder=batch_dir(batch_id)
    with rasterio.open(folder/'esri_rgb.tif') as src:
        rgb=src.read().transpose(1,2,0); bounds=src.bounds
    extent=[bounds.left,bounds.right,bounds.bottom,bounds.top]
    reference=load_original('classify_full_rectangle')
    colors={1:'#17becf',3:'#a4d65e',4:'#c88c47'} if combined else reference.COLORS
    names={1:'Combined water / trees / structures / roads / uncertain',3:'Crops / grass / low vegetation',4:'Bare soil / rock / sparse ground'} if combined else reference.NAMES
    fig,axs=plt.subplots(1,2,figsize=(20,7))
    for ax in axs: ax.imshow(rgb,extent=extent); ax.set_axis_off()
    if (folder/'classes.tif').exists():
        with rasterio.open(folder/'classes.tif') as src: classes=src.read(1)
        if combined:
            classes=classes.copy()
            classes[np.isin(classes,[1,2,5,6,7,8])]=1
        rgba=np.zeros((*classes.shape,4),'float32')
        for cls,color in colors.items():
            rgba[classes==cls]=[*matplotlib.colors.to_rgb(color),55/255 if combined else (.25 if cls!=8 else .12)]
        edge=find_boundaries(classes,mode='inner')&(classes>0); rgba[edge,3]=.9
        axs[1].imshow(rgba,extent=extent)
        frame=gpd.read_file(folder/'classified.gpkg',layer='classified_regions')
        if combined:
            # Match the user's reference: retain individual object outlines even
            # when adjacent objects share the same combined display class.
            for cls,color in colors.items():
                part=frame.loc[frame.combined_id==cls]
                if len(part):
                    part.boundary.plot(ax=axs[1],linewidth=.5,color=color,alpha=235/255)
        else:
            frame.boundary.plot(ax=axs[1],linewidth=.2,color='#eeeeee',alpha=.35)
        fig.legend(handles=[Patch(color=colors[c],label=n) for c,n in names.items()],loc='lower center',ncol=3 if combined else 4,fontsize=8)
    outline=gpd.GeoSeries([owned_geometry(batch_id)],crs=32643)
    for ax in axs: outline.boundary.plot(ax=ax,color='white',linewidth=.8)
    axs[0].set_title('Live Esri source — original ~0.485 m sampling')
    axs[1].set_title('Batch classification — provisional; white boundary = owned AOI portion' if (folder/'classes.tif').exists() else 'Source only — classification not yet produced')
    fig.suptitle(batch_id+' — PARTIAL whole-AOI run')
    target=folder/('preview_combined.png' if combined else 'preview.png')
    fig.tight_layout(rect=(0,.09,1,.95)); fig.savefig(target,dpi=125); plt.close(fig)
    return target

if __name__=='__main__':
    parser=argparse.ArgumentParser(); parser.add_argument('batch_id')
    parser.add_argument('--eight-classes',action='store_true')
    args=parser.parse_args()
    print(preview(args.batch_id,combined=not args.eight_classes))
