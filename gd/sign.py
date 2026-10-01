#!/usr/bin/env python3
"""Sign verified release artifacts in a separate job without running upstream code."""
from pathlib import Path
import base64
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile

root=Path(__file__).resolve().parents[1]
policy=json.loads((root/'gd/config.json').read_text())
incoming=Path(sys.argv[1]);output=Path(sys.argv[2]);output.mkdir(parents=True,exist_ok=True)
sdk=Path(os.environ.get('ANDROID_HOME',str(Path.home()/'Library/Android/sdk')))
versions=[p for p in (sdk/'build-tools').iterdir() if re.fullmatch(r'\d+\.\d+\.\d+',p.name)]
tools=max(versions,key=lambda p:tuple(map(int,p.name.split('.'))))
os.umask(0o077)
with tempfile.TemporaryDirectory(prefix='gd-support-sign-') as folder:
    secret=Path(folder)/'support.p12';password=Path(folder)/'password'
    secret.write_bytes(base64.b64decode(os.environ.pop('GD_SUPPORT_KEYSTORE_B64'),validate=True))
    password.write_text(os.environ.pop('GD_SUPPORT_STORE_PASSWORD'));secret.chmod(0o600);password.chmod(0o600)
    artifacts={}
    for receipt_path in sorted(incoming.rglob('build-receipt.json')):
        receipt=json.loads(receipt_path.read_text())
        if receipt['recipe_commit']!=os.environ['GD_BUILD_COMMIT'] or receipt['run_id']!=os.environ['GD_BUILD_RUN']:
            raise ValueError('Artifact provenance mismatch')
        if receipt['policy']!=policy:raise ValueError('Build policy mismatch')
        for filename,sha in receipt['artifacts'].items():
            if Path(filename).name!=filename:raise ValueError('Unexpected artifact path')
            source=receipt_path.parent/filename
            if hashlib.sha256(source.read_bytes()).hexdigest()!=sha:raise ValueError('Artifact digest mismatch')
            if filename.endswith('-unsigned.apk'):
                report=subprocess.check_output([tools/'aapt','dump','badging',source],text=True)
                match=re.search(r"package: name='([^']+)' versionCode='([0-9]+)' versionName='([^']+)'",report)
                native=re.search(r"^native-code: '([^']+)'$",report,re.M)
                if not match or match[1]!=policy['package'] or match[3]!=policy['version_name'] or 'application-debuggable' in report:
                    raise ValueError('Unexpected Android package')
                if not native or native[1] not in ('arm64-v8a','armeabi-v7a','x86_64'):raise ValueError('Unexpected native architecture')
                abi=native[1]
                if abi in artifacts:raise ValueError('Duplicate ABI')
                subprocess.run([tools/'zipalign','-c','-P','16','4',source],check=True,stdout=subprocess.DEVNULL)
                target=output/filename.replace('-unsigned.apk','.apk')
                subprocess.run([tools/'apksigner','sign','--ks',secret,'--ks-key-alias','gd-support','--ks-pass','file:'+str(password),'--out',target,source],check=True)
                verified=subprocess.check_output([tools/'apksigner','verify','--verbose','--print-certs',target],text=True)
                if re.findall(r'Signer #[0-9]+ certificate SHA-256 digest: ([a-f0-9]{64})',verified)!=[policy['certificate_sha256']]:
                    target.unlink();raise ValueError('Signing certificate mismatch')
                artifacts[abi]={'filename':target.name,'sha256':hashlib.sha256(target.read_bytes()).hexdigest(),'size':target.stat().st_size,'version_code':int(match[2])}
            elif filename.endswith('-source.tar.gz'):
                (output/filename).write_bytes(source.read_bytes())
            else:raise ValueError('Unexpected build artifact')
    if set(artifacts)!={'arm64-v8a','armeabi-v7a','x86_64'}:raise ValueError('Missing supported architecture')
    (output/'release-manifest.json').write_text(json.dumps({'recipe_commit':os.environ['GD_BUILD_COMMIT'],'run_id':os.environ['GD_BUILD_RUN'],'policy':policy,'artifacts':artifacts},indent=2)+'\n')
print('Verified and signed all three Android architectures.')
