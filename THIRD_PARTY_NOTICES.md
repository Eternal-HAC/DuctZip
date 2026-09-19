# Third-Party Notices

DuctZip is distributed under the MIT License; see [LICENSE](LICENSE).
This file records third-party components and their obligations.

## 7-Zip (backend, not bundled in this build)

DuctZip delegates archive algorithms to the 7-Zip command-line backend
(`7z.exe` / `7zz.exe`) discovered on the user's machine. This repository and
this portable build **do not bundle 7-Zip binaries** unless a `vendor/7zip`
directory is present, and that directory is added only after an explicit user
approval recorded in `LONG_TASK.md` §10.2 item 3 (exact source, version,
checksums, and license obligations presented and approved before download).

Bundling policy (approved 2026-09-19): the official standalone console
backend from 7-zip.org, pinned to an exact version; this file and
`dist/build-manifest.json` must then record the version, source URL,
SHA-256, and the license text below.

7-Zip is licensed under the GNU LGPL v2.1+ with a BSD-like clause for parts of
the code, plus the unRAR restriction for RAR-format support: the unRAR code
may not be used to develop a RAR compressor or to reverse-engineer the RAR
format; RAR extraction (decompression) and redistribution with those
conditions is permitted. Full text: <https://www.7-zip.org/license.txt>.

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
