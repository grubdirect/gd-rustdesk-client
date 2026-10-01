#!/usr/bin/env python3
"""Apply a small, fail-closed Android customization to exact upstream sources."""
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
POLICY = json.loads((ROOT/'gd/config.json').read_text())


def replace(path, old, new):
    text = path.read_text()
    if text.count(old) != 1:
        raise ValueError('Upstream source changed: '+str(path))
    path.write_text(text.replace(old, new))


def rust_map(values):
    pairs = ',\n'.join('        ('+json.dumps(k)+'.to_owned(), '+json.dumps(v)+'.to_owned())' for k,v in values.items())
    return 'RwLock::new(HashMap::from([\n'+pairs+'\n    ]))'


def prepare(source):
    for folder, sha in [(source, POLICY['upstream_commit']), (source/'libs/hbb_common', POLICY['common_commit'])]:
        if subprocess.check_output(['git','-C',str(folder),'rev-parse','HEAD'],text=True).strip()!=sha:
            raise ValueError('Unexpected source revision')
        if subprocess.check_output(['git','-C',str(folder),'status','--porcelain'],text=True).strip():
            raise ValueError('Refusing to patch a modified source checkout')
    server = POLICY['server']
    options = {
        'custom-rendezvous-server': server['host'], 'relay-server': server['relay'],
        'key': server['key'], 'api-server': server['api'], 'access-mode': 'custom',
        'enable-keyboard': 'N', 'enable-clipboard': 'N', 'enable-file-transfer': 'N',
        'enable-audio': 'N', 'enable-camera': 'N', 'enable-terminal': 'N',
        'enable-tunnel': 'N', 'enable-lan-discovery': 'N',
        'allow-remote-config-modification': 'N', 'approve-mode': 'click',
        'verification-method': 'use-temporary-password', 'allow-insecure-tls-fallback': 'N',
    }
    config = source/'libs/hbb_common/src/config.rs'
    replace(config,
        'pub static ref OVERWRITE_SETTINGS: RwLock<HashMap<String, String>> = Default::default();',
        '// GD Android distribution: network and view-only policy are fixed at build time.\n'
        '    pub static ref OVERWRITE_SETTINGS: RwLock<HashMap<String, String>> = '+rust_map(options)+';')
    replace(config,
        'pub static ref OVERWRITE_LOCAL_SETTINGS: RwLock<HashMap<String, String>> = Default::default();',
        'pub static ref OVERWRITE_LOCAL_SETTINGS: RwLock<HashMap<String, String>> = '+rust_map({'disable-floating-window':'Y','allow-remote-cm-modification':'N'})+';')
    # Also replace fallback constants: startup must never contact the public RustDesk service.
    replace(config, 'pub const RENDEZVOUS_SERVERS: &[&str] = &["rs-ny.rustdesk.com"];',
            'pub const RENDEZVOUS_SERVERS: &[&str] = &['+json.dumps(server['host'])+'];')
    replace(config, 'pub const RS_PUB_KEY: &str = "OeVuKk5nlHiXp+APNn0Y3pC1Iwpwn44JGqrQCsWqmBw=";',
            'pub const RS_PUB_KEY: &str = '+json.dumps(server['key'])+';')
    with config.open('a') as output:
        output.write('''
// Regression checks for the distributed GD configuration, not a network test.
#[cfg(test)]
mod gd_policy_tests {
    use super::*;
    #[test]
    fn gd_policy_rejects_server_and_permission_overrides() {
        let pinned = OVERWRITE_SETTINGS.read().unwrap().clone();
        for (name, expected) in pinned {
            Config::set_option(name.clone(), "untrusted-change".to_owned());
            assert_eq!(Config::get_option(&name), expected, "{}", name);
        }
        LocalConfig::set_option("disable-floating-window".to_owned(), "N".to_owned());
        assert_eq!(LocalConfig::get_option("disable-floating-window"), "Y");
        assert_eq!(Config::get_option("custom-rendezvous-server"), RENDEZVOUS_SERVERS[0]);
        assert_eq!(Config::get_option("key"), RS_PUB_KEY);
        assert_eq!(RENDEZVOUS_SERVERS.len(), 1);
    }
}
''')
    gradle = source/'flutter/android/app/build.gradle'
    replace(gradle, 'applicationId "com.carriez.flutter_hbb"', 'applicationId '+json.dumps(POLICY['package']))
    replace(gradle, 'signingConfig signingConfigs.release', '// Signed separately with the GD support release identity after verification.')
    manifest = source/'flutter/android/app/src/main/AndroidManifest.xml'
    replace(manifest, 'android:label="RustDesk"', 'android:label="'+POLICY['name']+'"')
    # Separate the URL handler from the official app during safe side-by-side migration.
    replace(manifest, '<data android:scheme="rustdesk" />', '<data android:scheme="gd-rustdesk" />')
    # Keep the upstream About/licence UI; expose the exact custom build's source there.
    common = source/'flutter/lib/mobile/pages/settings_page.dart'
    anchor = '          title: Text(translate("About")),\n          tiles: ['
    replace(common, anchor, anchor+'\n            SettingsTile(\n'
        '              title: const Text("GD Remote Support source (AGPL-3.0)"),\n'
        '              onPressed: (context) => launchUrlString('+json.dumps(POLICY['source_url'])+'),\n'
        '              leading: const Icon(Icons.code),\n'
        '            ),')
    server_model = source/'flutter/lib/models/server_model.dart'
    replace(server_model,
        '      if (!await AndroidPermissionManager.check(kManageExternalStorage)) {\n'
        '        await AndroidPermissionManager.request(kManageExternalStorage);\n'
        '      }',
        '      // GD: view-only sessions do not need access to files on the POS.\n'
        '      if ((await bind.mainGetOption(key: kOptionEnableFileTransfer)) != "N" &&\n'
        '          !await AndroidPermissionManager.check(kManageExternalStorage)) {\n'
        '        await AndroidPermissionManager.request(kManageExternalStorage);\n'
        '      }')
    # Retain upstream notices and mark the date and author of each modified file.
    notice = 'Modified by Grub Direct on 2026-10-01 for GD Remote Support; see GD-BUILD.json.'
    for modified in (config, gradle, common, server_model):
        modified.write_text('// '+notice+'\n'+modified.read_text())
    xml = manifest.read_text()
    declaration, rest = xml.split('\n', 1)
    manifest.write_text(declaration+'\n<!-- '+notice+' -->\n'+rest)
    (source/'GD-BUILD.json').write_text(json.dumps(POLICY,indent=2)+'\n')
    print('Applied pinned GD server, view-only policy and separate Android identity.')


if __name__=='__main__':
    prepare(Path(sys.argv[1]).resolve())
