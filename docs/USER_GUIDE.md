# FideliChem User Guide

This guide explains the normal desktop workflow for FideliChem, with special
attention to the first-run step that is easy to miss: creating or opening an
active workspace before importing evidence.

## 1. The two folders you must distinguish

FideliChem uses two different kinds of folders:

1. **Workspace (project) folder** — FideliChem's private catalog. It contains
   the project database, manifest, audit information, and generated exports.
2. **Evidence source** — files or folders produced by another scientific tool,
   such as an XLSX table, a MOL2 file, a docking run, or a GROMACS directory.

The evidence source is not the workspace. Create the workspace first, then
select the evidence source on the Import page.

Do not create a workspace inside a raw evidence folder. Keep them separate, for
example:

```text
C:\Users\you\Documents\FideliChem Projects\EGFR campaign\   <- workspace
C:\Users\you\Documents\Pipeline\ECBD_actives_mopac_v5\   <- evidence source
```

## 2. Start FideliChem

### Installed Windows or Linux build

Launch **FideliChem** from the Start menu, desktop shortcut, application menu,
or the executable included in the release package.

### Running from the source repository

From the repository directory:

```powershell
uv sync --locked
uv run fidelichem-gui
```

The application opens on the **Project** page. The sidebar badge initially
shows **No workspace selected**. This is expected; importing is intentionally
disabled until a project is active.

## 3. Create a new workspace (first use)

Use this procedure when you are starting a new campaign.

1. Select **Project** in the left sidebar.
2. In **Project name**, enter a readable name, such as
   `EGFR Virtual Screening`.
3. In **Storage folder path**, enter the location where FideliChem should
   create the project. You may click **Choose Folder**.
4. Choose a new folder or an existing empty folder. Do not choose the folder
   containing your MOL2, XLSX, docking, or simulation files.
5. Click **Create Project**.
6. Wait for the confirmation. The Project page shows **Active Project**, the
   sidebar badge displays the project name and path, and the status bar says
   **Workspace ready**.

The workspace folder is created with this layout:

```text
<workspace>\
├── project.json
├── project.fidelichem.sqlite
├── artifacts\
├── cache\
├── exports\
└── logs\
```

FideliChem refuses to overwrite a non-empty folder. If creation fails, select
an empty folder or create a new one and try again.

## 4. Open an existing workspace

Use this procedure when the project was already created on this computer or
was copied from another location.

1. Select **Project**.
2. Put the path of the project root in **Storage folder path**, or click
   **Choose Folder**.
3. Click **Open**.
4. Confirm that the sidebar badge shows the project name and that the status
   bar says **Workspace opened**.

Select the folder that directly contains `project.json` and
`project.fidelichem.sqlite`. Selecting a raw pipeline folder, a parent folder,
or an individual database file will not open a workspace.

If the project was moved, move the entire project folder without renaming or
editing its manifest. The database and manifest must remain together.

## 5. Confirm that a workspace is active

Before importing, check all three indicators:

- The sidebar badge no longer says **No workspace selected**.
- The Project page shows **Active Project** or **Opened workspace**.
- On the Import page, **Execute Import** becomes enabled after a valid source
  path is entered.

**Probe Data** can be used before a workspace is active. **Execute Import**
cannot; this prevents evidence from being written to an undefined project.

## 6. Import scientific evidence

### Basic workflow

1. Create or open a workspace as described above.
2. Select **Import** in the sidebar.
3. Leave **Adapter** set to `auto` unless you know which adapter is required.
4. Select the evidence with **Choose Folder** or **Choose File**.
5. Click **Probe Data**.
6. Read the **Probe Preview**. It reports the detected format, suggested
   adapter, and confidence.
7. If the preview is appropriate, click **Execute Import**.
8. Wait for **Import completed**. The preview reports the batch ID, adapter,
   compound count, and validation warnings.

The source is hashed when the plan is created. Do not edit, rename, or move
the source files between **Probe Data** and **Execute Import**.

### Supported source examples

The file chooser accepts common evidence formats, including:

- CSV and TSV tables;
- tab-delimited TXT tables;
- JSON and JSONL descriptors;
- XLSX/XLSM spreadsheets;
- MOL2 structures;
- folders produced by GOLD, SMILES2Docking, DockLens, GROMACS, or
  MolDynStudio.

For a table import, the automatic adapter looks for identity columns such as
compound ID, access code, and SMILES, plus score or measurement columns. If the
preview reports no compatible adapter, inspect the headers and select the
appropriate adapter manually.

### Importing a single MOL2 file

For a SMILES2Docking export, it is sufficient to choose
`prepared_ligands.mol2`. FideliChem automatically looks for adjacent
`run_report*.json`, `run.json`, `manifest.json`, or SMILES2Docking descriptor
files in the same folder. These reports may reference the original XLSX used
to recover compound identities.

If the MOL2 file has no identity metadata or adjacent report, the import may
complete with QC messages for missing identities. Review those messages rather
than treating an unknown identity as a valid compound.

### Choosing an adapter manually

Use the Adapter menu when automatic probing is ambiguous:

| Adapter | Typical evidence |
| --- | --- |
| `universal_table` | CSV, TSV, TXT, JSON, JSONL, XLSX/XLSM tables |
| `smiles2docking` | Prepared SDF/MOL2 structures and preparation reports |
| `smiles2select` | Compound selection campaigns |
| `gold` | CCDC GOLD docking directories |
| `docklens` | Interaction/contact reports |
| `gromacs` | GROMACS XVG and run evidence |
| `moldynstudio` | MolDynStudio manifests and metrics |

Probe again after changing the adapter.

## 7. After an import

Use the sidebar pages to inspect the persisted evidence:

- **Compounds** — canonical compound identities and molecular states;
- **Docking** — scores, runs, poses, and rankings;
- **Interactions** — residue contacts and interaction summaries;
- **Dynamics** — simulation runs and metric curves;
- **Decision** — deterministic triage and explanations;
- **QC** — warnings, missing fields, and records needing review;
- **Exports** — reproducible output packages.

An import is an audited batch. Raw source files are not overwritten, and
missing data is retained as missing rather than silently changed to zero.

## 8. Export results

1. Confirm that a workspace is active and that at least one import completed.
2. Select **Exports**.
3. Choose a format: CSV, Excel (XLSX), Parquet, JSON Bundle, or Full Audit
   Report.
4. Choose an output folder. The default is the workspace's `exports` folder.
5. Select the evidence sections to include.
6. Click **Generate Export**.

The generated package includes provenance information when that option is
selected. Keep the generated manifest with the exported files.

## 9. Troubleshooting

### “Execute Import” is disabled

This normally means there is no active workspace, or no source path has been
entered.

1. Return to **Project**.
2. Create a new project or open the folder containing `project.json`.
3. Return to **Import** and select the evidence source.

### The sidebar still says “No workspace selected”

The project action did not complete. Read the Project page status message and
check that:

- the path exists and is writable;
- a new project path is empty when creating a project;
- an existing project path contains both `project.json` and
  `project.fidelichem.sqlite` when opening one.

### “No compatible evidence adapter detected”

Check that you selected the actual file or run folder, not its parent directory.
Use **Choose File** for one file and **Choose Folder** for a complete run.
Probe with a specific adapter if automatic detection is uncertain.

### The preview is correct but import fails

Check the detailed message in the preview and status bar, then:

- verify that the source files still exist and were not changed after probing;
- verify read permissions for the source and write permissions for the
  workspace;
- make sure the workspace has not been opened by another process in a way that
  locks its SQLite database;
- review `<workspace>\logs` for the application log.

### A project will not open

Choose the project root, not the evidence folder. The root must contain the
standard directories and both project files. Do not manually edit
`project.json`; recreate or restore the complete project folder if it is
damaged.

## 10. Recommended first test

For a quick end-to-end check:

1. Create an empty workspace named `FideliChem Test`.
2. Open **Import** and choose a small CSV, TXT, XLSX, or MOL2 source.
3. Click **Probe Data** and confirm a detected adapter appears.
4. Click **Execute Import**.
5. Open **Compounds** and **QC** to review the result.
6. Generate a CSV export from **Exports**.

Once this works, repeat the same procedure with the full pipeline folder.

## 11. Safety and provenance

FideliChem reads imported evidence; it does not execute scripts or scientific
programs from the selected source. Keep original evidence immutable and retain
the workspace database, logs, and export manifests for auditability.

FideliChem is authored by **Adriano Marques Gonçalves (UNIARA)**. The source
code is distributed under the MIT License; third-party component licenses are
listed in `THIRD_PARTY_NOTICES.md`.
