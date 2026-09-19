# Third-Party Notices

DuctZip is distributed under the MIT License; see [LICENSE](LICENSE).
This file records third-party components and their obligations.

## 7-Zip (bundled backend)

DuctZip delegates archive algorithms to the 7-Zip command-line backend. A
standalone console backend is **bundled** in this repository under
[`vendor/7zip/`](vendor/7zip/) and is included in the portable build; the
discovery chain still prefers a user-specified backend over the bundled one, and
falls back to a system installation when no bundled copy is present.

### Bundled artifact

| Item | Value |
| --- | --- |
| Component | 7-Zip standalone console backend (`7z.exe` + `7z.dll`) |
| Version | **26.03 (x64)**, build date 2026-09-03 |
| Upstream installer | `7z2603-x64.exe` |
| Source URL | <https://www.7-zip.org/a/7z2603-x64.exe> |
| Resolved origin | <https://github.com/ip7z/7zip/releases/download/26.03/7z2603-x64.exe> |
| Download date | 2026-09-19 |
| Licensing | GNU LGPL v2.1+ (parts under a BSD-like clause) + unRAR restriction |

SHA-256 checksums (measured locally with `Get-FileHash -Algorithm SHA256` and
`sha256sum`; see also `dist/build-manifest.json` for the per-file record):

| File | SHA-256 |
| --- | --- |
| `7z2603-x64.exe` (installer) | `0859c524b8a63551848f0c246abddcb1d0b7b656b0fbfe879f8d85e61a9e6edd` |
| `vendor/7zip/7z.exe` | `6ee3c0ed0b27663c1b948ae85a7c0bb073aed1498983182f3f0df1f6a8c30b2f` |
| `vendor/7zip/7z.dll` | `65e4c1f855f9ef6e8f0f5df8e3f27d9eb5f07311408639da0a1ca0b8f4871b0d` |
| `vendor/7zip/License.txt` | `519ac0a4bded9c18ea02e0afb71f663d8c47373bd9facd3ac96a79f51d77765d` |

### How the artifact was verified

Approval was conditioned on verifying "TLS + Authenticode" (`LONG_TASK.md`
§10.2 item 3). **The Authenticode half cannot be satisfied: upstream 7-Zip does
not Authenticode-sign its Windows binaries.** This was confirmed independently
two ways — the PE certificate-table data directory of `7z2603-x64.exe` is all
zeroes, and the locally installed 7-Zip 24.08 `7z.exe` / `7z.dll` report
`NotSigned` as well — so this is an upstream property, not a local chain or
trust-store failure. The official download page publishes no checksums and no
signatures either.

The user reviewed this and approved a substitute verification chain on
2026-09-19 (recorded in `PROGRESS.md`; DD-008 amended accordingly):

1. **TLS** — `https://www.7-zip.org/a/7z2603-x64.exe` over HTTPS, redirecting to
   the canonical upstream release at `github.com/ip7z/7zip`.
2. **Published digest** — the GitHub release metadata for tag `26.03` publishes
   `sha256:0859c524b8a63551848f0c246abddcb1d0b7b656b0fbfe879f8d85e61a9e6edd`
   for this asset.
3. **Measured hash** — the downloaded installer hashes to exactly that value.
4. **Payload identity** — extracting the installer with an independent 7-Zip
   yields a backend that self-reports `7-Zip 26.03 (x64) ... 2026-09-03`.

**Residual supply-chain limitation (stated deliberately, not hidden):** the
bundled binaries carry no cryptographic publisher signature, so authenticity
rests on transport security plus the upstream-published digest rather than on a
code-signing certificate. Users who require signed third-party binaries should
not use the bundled backend; set an explicit `--sevenzip` path or
`DUCTZIP_7Z_PATH` to a backend they trust. This limitation is repeated in
`docs/SECURITY.md` and in the release notes.

### License obligations

7-Zip is licensed under the GNU LGPL v2.1+ with a BSD-like clause for parts of
the code, plus the unRAR restriction for RAR-format support: the unRAR code may
not be used to develop a RAR compressor or to reverse-engineer the RAR format;
RAR extraction (decompression) and redistribution under those conditions is
permitted. The upstream license text is redistributed verbatim as
[`vendor/7zip/License.txt`](vendor/7zip/License.txt); the canonical copy is
<https://www.7-zip.org/license.txt>. DuctZip's own source is MIT-licensed and
does not link 7-Zip libraries — the bundled backend is invoked as a separate
process.

## Python (runtime requirement, not distributed)

DuctZip requires Python 3.11+ from the user's environment and does not
distribute it. Python is licensed under the PSF License:
<https://docs.python.org/3/license.html>.

## PySide6 (optional GUI dependency, not bundled)

The GUI requires PySide6, installed separately by the user
(`python -m pip install PySide6`). PySide6 is available under LGPL v3 /
GPL v3: <https://www.qt.io/licensing/open-source-lgpl-obligations>.
DuctZip's own code does not link PySide6 at import time unless the GUI is
launched.
