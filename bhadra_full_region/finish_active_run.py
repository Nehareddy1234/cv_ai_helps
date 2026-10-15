"""Finish classification after the currently running SAM tile job completes."""
from pathlib import Path
import json
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parent
deadline=time.monotonic()+6*3600
manifest=json.loads((ROOT/'cache/manifest.json').read_text())
while True:
    complete=all((ROOT/f'cache/tile_{job["tile"]}.json').exists() and
                 (ROOT/f'cache/tile_{job["tile"]}.npz').exists() for job in manifest['jobs'])
    if complete: break
    if time.monotonic()>deadline:
        raise TimeoutError('SAM tiles are still incomplete after six hours; no final result claimed')
    time.sleep(15)
print('All SAM caches present; composing and classifying whole Bhadra',flush=True)
with (ROOT/'classification_run.log').open('w') as log:
    result=subprocess.run([sys.executable,'-u',str(ROOT/'classify_bhadra.py')],cwd=ROOT,stdout=log,stderr=subprocess.STDOUT)
if result.returncode:
    raise RuntimeError(f'Classification failed with exit code {result.returncode}; see classification_run.log')
print((ROOT/'output/verification.json').read_text(),flush=True)
