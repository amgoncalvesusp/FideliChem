# FideliChem third-party notices

FideliChem's own source code is licensed under the MIT License by Adriano
Marques Gonçalves (UNIARA). The installer and portable bundles also contain
software from the projects below.
Those components keep their own licenses; this file does not relicense them.

## Runtime dependencies

| Component | Version range in FideliChem | License | Notice/source |
| --- | --- | --- | --- |
| CPython runtime | 3.12 | PSF-2.0 | [Python license](https://docs.python.org/3/license.html) |
| PySide6, PySide6-Essentials, PySide6-Addons, shiboken6 | 6.x | LGPL-3.0-only **or** GPL-2.0-only/GPL-3.0-only **or** commercial Qt license | [Qt for Python licensing](https://doc.qt.io/qtforpython-6/commercial/index.html) |
| PyInstaller bootloader | 6.16.0 (release build tool) | GPL-2.0-or-later with bootloader exception | [PyInstaller license](https://github.com/pyinstaller/pyinstaller/blob/main/COPYING.txt) |
| RDKit | 2026.3.4 | BSD 3-Clause | [RDKit license](https://github.com/rdkit/rdkit/blob/master/license.txt) |
| NumPy (transitive) | 2.x | BSD-3-Clause and bundled 0BSD/MIT/Zlib/CC0 notices | [NumPy licenses](https://numpy.org/doc/stable/license.html) |
| Pillow (transitive) | 12.x | MIT-CMU | [Pillow license](https://github.com/python-pillow/Pillow/blob/main/LICENSE) |
| Pydantic | 2.x | MIT | [Pydantic license](https://github.com/pydantic/pydantic/blob/main/LICENSE) |
| SQLAlchemy | 2.x | MIT | [SQLAlchemy license](https://github.com/sqlalchemy/sqlalchemy/blob/main/LICENSE) |
| Alembic | 1.x | MIT | [Alembic license](https://github.com/sqlalchemy/alembic/blob/main/LICENSE) |
| Mako (transitive) | 1.x | MIT | [Mako license](https://github.com/sqlalchemy/mako/blob/master/LICENSE) |
| greenlet (transitive) | 3.x | MIT and PSF-2.0 | [greenlet license](https://github.com/python-greenlet/greenlet/blob/main/LICENSE) |
| xlrd | 2.x | BSD | [xlrd license](https://github.com/python-excel/xlrd/blob/master/LICENSE) |
| typing-extensions (transitive) | 4.x | PSF-2.0 | [typing-extensions license](https://github.com/python/typing_extensions/blob/main/LICENSE) |

## Distribution obligations

The PySide6 distribution is not MIT. FideliChem must preserve the applicable
Qt/LGPL notices when it distributes the frozen Windows or Linux application.
The release pipeline therefore ships this notice file with every installer.
If FideliChem modifies Qt/PySide6 or links Qt in a way that changes the LGPL
requirements, the corresponding source and relinking obligations must also be
provided. A commercial Qt license is an alternative for products that cannot
meet the LGPL/GPL terms; it is not assumed by this repository.

The BSD, MIT, PSF, 0BSD, Zlib, and CC0 components are permissive and compatible
with an MIT license for FideliChem's own code, provided their copyright and
license notices remain available. This is a compatibility assessment, not
legal advice; have counsel review the final binary distribution if the product
will be sold or redistributed under a closed-source model.

## Project-license decision

Assessment: FideliChem's own source uses MIT; none of the runtime dependencies
requires the application to adopt a stronger copyleft license.
The repository must still keep this file and the upstream notices, and it must
not describe Qt, PySide6, RDKit, NumPy, or Python as MIT. Before publishing a
tag, add the selected project `LICENSE` file and its SPDX metadata to
`pyproject.toml`.
