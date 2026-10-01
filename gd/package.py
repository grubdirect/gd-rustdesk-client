#!/usr/bin/env python3
"""Keep modified corresponding source alongside every candidate APK."""
from pathlib import Path
import hashlib
import json
import os
import shutil
import tarfile

root=Path(__file__).resolve().parents[1]
policy=json.loads((root/'gd/config.json').read_text())
abi=os.environ['GD_BUILD_ABI']
out=root/'artifacts';out.mkdir(exist_ok=True)
apk=root/'source/flutter/build/app/outputs/flutter-apk'/('app-'+abi+'-release.apk')
shutil.copyfile(apk,out/('gd-support-'+policy['version_name']+'-'+abi+'-unsigned.apk'))
excluded={'.git','target','build','.dart_tool','.gradle','.pub-cache','jniLibs'}
with tarfile.open(out/('gd-support-'+policy['version_name']+'-'+abi+'-source.tar.gz'),'w:gz') as archive:
    for p in sorted((root/'source').rglob('*')):
        relative=p.relative_to(root/'source')
        if any(part in excluded for part in relative.parts) or p.name=='local.properties':continue
        if p.is_file() and not p.is_symlink():archive.add(p,arcname='source/'+str(relative),recursive=False)
    for directory in ('gd','.github'):
        for p in sorted((root/directory).rglob('*')):
            if p.is_file() and '__pycache__' not in p.parts:archive.add(p,arcname='recipe/'+str(p.relative_to(root)),recursive=False)
    for name in ('README.md','LICENCE'):archive.add(root/name,arcname='recipe/'+name)
receipt={'recipe_commit':os.environ['GD_BUILD_COMMIT'],'run_id':os.environ['GD_BUILD_RUN'],'policy':policy,
         'artifacts':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in out.iterdir() if p.is_file()}}
(out/'build-receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
