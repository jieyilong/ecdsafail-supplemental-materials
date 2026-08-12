# ECDSA.Fail frontier reconstruction at the 50% data cutoff

This directory contains the data and code used to reproduce Figure 7 and the
frontier analysis in Section 5.4 of the ECDSA.Fail paper. It reconstructs the
selected historical points under three admission rules from pinned public data.

## Confirmed data cutoff

- Submission: `8e9c9a2`
- Source commit: `60d61859fa6965eba53634f91877b1141a6f9dce`
- Data cutoff: `2026-07-26T09:21:55.494Z`
- Metrics: `Q=1151`, `T=1299453`, `Q*T=1495670403`
- Criterion: first promoted submission with an official score at or below half
  of the Google/Babbush low-gate comparison product used in Section 5.

## Results

- 831 rows in the pinned official API response
- 826 rows created by the data cutoff
- 576 pre-cut rows with structured Q/T metrics
- 15 manifest-selected historical display points
- 8 Pareto points in the paper's admitted set
- 16 Pareto points under the public-note-parser sensitivity rule
- 15 Pareto points under the API-metric-bearing sensitivity rule

The package does not rerun circuits, prove correctness for all inputs, or
claim that the retrospective API response is an exhaustive historical
database.

## Contents

- `data/raw/`: exact public source snapshots used by the reconstruction
- `data/curation/`: data cutoff, selection manifest, and admission rules
- `scripts/reconstruct.py`: deterministic offline reconstruction
- `scripts/verify_paper_integration.py`: compiled-paper consistency checks
- `tests/`: reconstruction and paper-integration tests
- `output/`: generated CSVs, figures, manifests, and verification report
- `output/pareto_manifest.csv`: the eight paper-admitted points with submission
  IDs, source commits, metrics, status, and public-note evidence

## Rebuild

Python 3.10 or newer is required.

```bash
python3 -m pip install -r requirements.txt
python3 scripts/reconstruct.py --output output
python3 -m unittest discover -s tests -v
```

To check a compiled paper:

```bash
python3 scripts/verify_paper_integration.py \
  --pdf /path/to/paper.pdf \
  --render-dir paper-pages \
  --report paper-verification.json
```

The compiled-paper check requires Poppler's `pdfinfo` and `pdftotext`; page
rendering also requires `pdftoppm`.

## Data boundary

The source files are snapshots of the public ECDSA.Fail submissions API, a
public Pareto Mirror checkpoint, and Teddy Pender's published chronology.
Public solver names, profile references, submission identifiers, commits, and
submission notes are retained for provenance and admission-rule reproduction.

Raw snapshots can contain submitter-supplied text, including usernames,
repository references, and local paths that submitters published. The snapshots
are retained byte-for-byte to preserve source integrity and must be treated as
untrusted data. The package adds no authentication material, private chats,
private meeting material, paper source, or local compilation logs.
`SHA256SUMS` pins every distributed file.

## Paper alignment

The reconstruction matches the paper's confirmed 26 July data cutoff, the
eight-point archive-conditioned Pareto set, and the 15-point historical display.
The generated `output/frontier_figure_paper.pdf` is the source for Figure 7.
