# GD Remote Support for Android

Grub Direct's preconfigured Android distribution of RustDesk, built from the exact
upstream and submodule revisions in [gd/config.json](gd/config.json). The small
customization is fully described by [gd/prepare.py](gd/prepare.py). Upstream source
and notices are retained under [AGPL-3.0](LICENCE).

Initial downstream changes: **1 October 2026**. Modified files identify Grub Direct
and the modification date; upstream copyright and licence notices are retained.

The client uses Grub Direct's ID/relay server and its **public** key, has the
floating shortcut disabled, and allows view-only sessions following approval on
the Android device. It contains no shared password, enrolment credential, server
private key or APK signing key. Android's screen-capture consent is unchanged.

The Android package `uk.co.grubdirect.support` is separate from the official
`com.carriez.flutter_hbb` app. This permits testing without uninstalling the old
client or overwriting its identity, settings or permissions. Use **GD Remote
Support** on the POS and the normal RustDesk desktop app on the operator's Mac.
Existing support mappings must be verified against the new app's displayed ID.

Builds use pinned RustDesk sources, Flutter 3.24.5, Rust 1.75, Android NDK r28c and
the upstream-pinned vcpkg revision. Host-side policy regression tests use Rust
1.88.0 for upstream test-only dependencies; Android APKs retain Rust 1.75. See the workflow for the complete build recipe.
Each build produces an unsigned release APK and a corresponding-source archive
including the patched submodule and this recipe. Release APKs are signed with a
dedicated Grub Direct support certificate after artifact verification.

The client is not an unattended-access bypass. The customer starts screen sharing
and approves the connection. It does not grant accessibility, file access, audio
capture or permanent passwords. The current support server's network restrictions
remain in effect; preconfiguration does not make it reachable from new networks.

This project is a downstream distribution, not an official RustDesk release.
