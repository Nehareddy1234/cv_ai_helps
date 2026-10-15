"""Diagnostic only: inspect water evidence in the reviewed audit coordinates."""
from pathlib import Path
import rasterio
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from scipy import ndimage as ndi
ROOT=Path(__file__).resolve().parent
with rasterio.open(ROOT/'data/esri_test_aligned.tif') as src:
    rgb=src.read()
r,g,b=ndi.gaussian_filter(rgb.astype(float),sigma=(0,1,1))
evidence=(r<90)&(r<g*.94)&(b>g*.73)&(g<115)
with rasterio.open(ROOT/'output/reviewed_classes.tif') as src:
    water=src.read(1)==1
fig,axs=plt.subplots(1,2,figsize=(15,9))
for ax in axs:
    ax.imshow(rgb.transpose(1,2,0),extent=(20,2025,1120,30))
    ax.set_xlim(330,1000); ax.set_ylim(740,320); ax.grid(alpha=.4)
overlay=np.zeros((*evidence.shape,4)); overlay[evidence]=[0,1,1,.5]
axs[1].imshow(overlay,extent=(20,2025,1120,30))
axs[0].set_title('River reach: original imagery / audit pixel coordinates')
axs[1].set_title('Cyan = RGB water evidence (not final classes)')
fig.tight_layout(); fig.savefig(ROOT/'output/water_evidence_audit.png',dpi=130)
