"""Render a coordinate-labelled industrial crop for prompt review."""
from pathlib import Path
import rasterio
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
ROOT=Path(__file__).resolve().parent
with rasterio.open(ROOT/'data/esri_test_aligned.tif') as src:
    rgb=src.read().transpose(1,2,0)
fig,ax=plt.subplots(figsize=(10,11))
ax.imshow(rgb,extent=(20,2025,1120,30))
ax.set_xlim(730,1140); ax.set_ylim(960,540)
ax.set_xticks(range(740,1141,20)); ax.set_yticks(range(540,961,20))
ax.grid(alpha=.25); ax.set_title('Industrial structures: audit-image coordinates')
fig.tight_layout(); fig.savefig(ROOT/'output/industrial_source_audit.png',dpi=130)
