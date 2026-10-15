from pathlib import Path
import json
import numpy as np
import rasterio
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
ROOT=Path(__file__).resolve().parent
with rasterio.open(ROOT/'data/esri_test_aligned.tif') as src: rgb=src.read().transpose(1,2,0)
masks=np.load(ROOT/'output/prompted_land_masks.npz')
audit=json.loads((ROOT/'output/land_prompts.json').read_text())
fig,axs=plt.subplots(2,2,figsize=(14,11))
for ax,name in zip(axs.ravel(),masks.files):
    job=audit['prompts_in_audit_image'][name]
    ax.imshow(rgb,extent=(20,2025,1120,30))
    overlay=np.zeros((*masks[name].shape,4)); overlay[masks[name]]=[1,0,1,.26]
    ax.imshow(overlay,extent=(20,2025,1120,30))
    x0,y0,x1,y1=job['box']; ax.set_xlim(x0,x1); ax.set_ylim(y1,y0)
    for pts,c in [(job['positive'],'lime'),(job['negative'],'red')]:
        ax.scatter(*np.array(pts).T,c=c,s=20)
    score=audit['sam_scores_not_class_probabilities'][name]
    ax.set_title(f'{name}: SAM score {score:.2f} (not class probability)')
fig.tight_layout(); fig.savefig(ROOT/'output/land_prompts_preview.png',dpi=120)
