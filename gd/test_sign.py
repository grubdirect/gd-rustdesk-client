"""Exercise release verification using real Android tools and a throwaway key."""
import base64
import hashlib
import json
import os
import re
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile


class SigningBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / 'gd').mkdir()
        shutil.copyfile(Path(__file__).with_name('sign.py'), self.root / 'gd/sign.py')
        self.policy = json.loads(Path(__file__).with_name('config.json').read_text())
        sdk = Path(os.environ.get('ANDROID_HOME', str(Path.home() / 'Library/Android/sdk')))
        self.tools = max((p for p in (sdk / 'build-tools').iterdir() if re.fullmatch(r'\d+\.\d+\.\d+', p.name)), key=lambda p: tuple(map(int, p.name.split('.'))))
        self.android = sdk / 'platforms/android-35/android.jar'
        self.run_tool('keytool', '-genkeypair', '-keystore', self.root / 'test.p12', '-storepass', 'test-only-password', '-alias', 'gd-support', '-keyalg', 'RSA', '-keysize', '2048', '-validity', '1', '-dname', 'CN=Test Only', '-noprompt')
        cert = subprocess.check_output(['keytool', '-exportcert', '-keystore', str(self.root / 'test.p12'), '-storepass', 'test-only-password', '-alias', 'gd-support'])
        self.policy['certificate_sha256'] = hashlib.sha256(cert).hexdigest()
        (self.root / 'gd/config.json').write_text(json.dumps(self.policy))
        self.environment = dict(os.environ, GD_BUILD_COMMIT='reviewed-commit', GD_BUILD_RUN='1', GD_SUPPORT_KEYSTORE_B64=base64.b64encode((self.root / 'test.p12').read_bytes()).decode(), GD_SUPPORT_STORE_PASSWORD='test-only-password')
        for abi in ('arm64-v8a', 'armeabi-v7a', 'x86_64'):
            self.fixture(abi)

    def run_tool(self, *args):
        subprocess.run([str(a) for a in args], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)

    def fixture(self, abi, package=None, debug=False):
        folder = self.root / 'incoming' / abi
        folder.mkdir(parents=True, exist_ok=True)
        manifest = folder / 'AndroidManifest.xml'
        manifest.write_text('<manifest xmlns:android="http://schemas.android.com/apk/res/android" package="'+(package or self.policy['package'])+'" android:versionCode="'+str({'armeabi-v7a':1000,'arm64-v8a':2000,'x86_64':4000}[abi]+self.policy['build_number'])+'" android:versionName="'+self.policy['version_name']+'"><uses-sdk android:minSdkVersion="22" android:targetSdkVersion="33"/><application android:debuggable="'+str(debug).lower()+'"/></manifest>')
        raw = folder / 'raw.apk'
        self.run_tool(self.tools / 'aapt', 'package', '-f', '-M', manifest, '-I', self.android, '-F', raw)
        with zipfile.ZipFile(raw, 'a') as archive:
            archive.writestr('lib/'+abi+'/libfixture.so', b'test fixture, not executable', compress_type=zipfile.ZIP_DEFLATED)
        apk = folder / (abi+'-unsigned.apk')
        self.run_tool(self.tools / 'zipalign', '-f', '-P', '16', '4', raw, apk)
        source = folder / (abi+'-source.tar.gz')
        source.write_bytes(b'fixture source archive')
        receipt = dict(recipe_commit='reviewed-commit', run_id='1', policy=self.policy, artifacts={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (apk, source)})
        (folder / 'build-receipt.json').write_text(json.dumps(receipt))

    def sign(self):
        return subprocess.run([sys.executable, str(self.root / 'gd/sign.py'), str(self.root / 'incoming'), str(self.root / 'signed')], env=self.environment, text=True, capture_output=True)

    def test_real_signatures_and_complete_manifest(self):
        result = self.sign()
        self.assertEqual(0, result.returncode, result.stderr)
        manifest = json.loads((self.root / 'signed/release-manifest.json').read_text())
        self.assertEqual({'arm64-v8a','armeabi-v7a','x86_64'}, set(manifest['artifacts']))
        for artifact in manifest['artifacts'].values():
            self.run_tool(self.tools / 'apksigner', 'verify', self.root / 'signed' / artifact['filename'])

    def test_modified_apk_is_rejected_before_release(self):
        with (self.root / 'incoming/arm64-v8a/arm64-v8a-unsigned.apk').open('ab') as apk:
            apk.write(b'tampered')
        self.assertIn('Artifact digest mismatch', self.sign().stderr)
        self.assertFalse((self.root / 'signed/release-manifest.json').exists())

    def test_debuggable_or_wrong_package_is_rejected(self):
        for package, debug in [('evil.application', False), (None, True)]:
            self.fixture('arm64-v8a', package, debug)
            self.assertIn('Unexpected Android package', self.sign().stderr)

    def test_different_build_receipt_is_rejected(self):
        self.environment['GD_BUILD_COMMIT'] = 'unreviewed-commit'
        self.assertIn('Artifact provenance mismatch', self.sign().stderr)

    def test_unapproved_signing_key_is_rejected(self):
        self.policy['certificate_sha256'] = '0'*64
        (self.root / 'gd/config.json').write_text(json.dumps(self.policy))
        for abi in ('arm64-v8a','armeabi-v7a','x86_64'):
            self.fixture(abi)
        self.assertIn('Signing certificate mismatch', self.sign().stderr)

    def test_incomplete_architectures_never_create_release_manifest(self):
        shutil.rmtree(self.root / 'incoming/x86_64')
        self.assertIn('Missing supported architecture', self.sign().stderr)
        self.assertFalse((self.root / 'signed/release-manifest.json').exists())


if __name__ == '__main__':
    unittest.main()
