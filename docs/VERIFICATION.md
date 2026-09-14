# Mac preview validation

Validated on 2026-09-14 using a Mac Apple Silicon development machine and
MuMu 1.4.11, rooted ARM64 Android, Nulls 15.535.13 / resources 15.535.86.
This is not a clean second-Mac certification.

- 33 Python tests: 31 passed, 2 optional user-HTML fixtures skipped.
- Bundled Frida 17.17.0: temporarily removed the existing server, verified fresh
  deployment from the bundled archive, executable version, and checksum.
- Used MuMu's bundled ADB without the Android SDK ADB path.
- Loaded a 75-event replay twice. Both completed at tick 4586.
- Headless precompute: 0.201 s and 0.190 s, excluding game initialization.
- Exact cached seeks to ticks 1200, 600 and 4586 passed on each load.
- Exit stopped Frida and removed the application's IPv4/IPv6 offline rules.
- Packaged ARM64 application starts; ad-hoc signature verifies.
- Observed one MuMu cold-boot IPlatformCompat startup failure; the application
  now retries this specific failure once, with separate regression coverage.

Remaining distribution checks: Developer ID signing and notarization,
quarantine-marked download launch on another Mac, other MuMu versions/install
locations/multi-instance ports. Windows and Intel Mac remain unsupported.
