# Appendix sources

LaTeX sources for the three appendix PDFs published one directory up. Each
appendix is a standalone document that reproduces the corresponding appendix of
the ECDSA.Fail paper, keeping the paper's own section, figure, and table
numbers so that a cross-reference carries the same number in both documents.

| Source           | Published PDF                                              |
| ---------------- | ---------------------------------------------------------- |
| `appendix-A.tex` | [`../detailed_results_and_circuit_improvement_trajectory.pdf`](../detailed_results_and_circuit_improvement_trajectory.pdf) |
| `appendix-B.tex` | [`../anatomy_of_agent_identified_quantum_circuit_optimizations.pdf`](../anatomy_of_agent_identified_quantum_circuit_optimizations.pdf) |
| `appendix-C.tex` | [`../optimization_census_of_accepted_competition_source_commits.pdf`](../optimization_census_of_accepted_competition_source_commits.pdf) |

## Building

Requires the LNCS bundle, which provides both `llncs.cls` and `splncs04.bst`.
It is not part of a base TeX Live install:

    tlmgr install llncs        # or: tlmgr --usermode install llncs

Then, for each appendix (three passes, because bibtex resolves the citations):

    pdflatex appendix-A && bibtex appendix-A \
      && pdflatex appendix-A && pdflatex appendix-A

No `.bbl` is checked in: `refs.bib` is here and each document calls
`\bibliography{refs}`, so bibtex regenerates the bibliography. Anyone who has
`llncs.cls` also has `splncs04.bst`, since they ship in the same package.

Note that `appendix-C` cites nothing, so bibtex reports `I found no \citation
commands` and exits non-zero. This is harmless — it still writes an empty
bibliography and the PDF builds correctly — but a build script that stops on a
non-zero exit status needs to tolerate it.

## Layout

- `appendix-{A,B,C}.tex` — the drivers: title block, counter offsets that
  restore the paper's numbering, and the bibliography.
- `appendix-{A,B,C}-content.tex` — the appendix bodies.
- `main-refs.tex` — `\newlabel` definitions extracted from the paper's
  `main.aux`, so references into the main paper render as real numbers without
  needing the paper tree at build time.
- `preamble.tex`, `preamble-body.tex`, `ZZ_header.tex`, `macros.tex` — shared
  preamble, mirroring the paper's, so typography and macros match.
- `refs.bib` — bibliography database.

The content and `main-refs.tex` files are snapshots generated upstream from the
paper source by that repository's `tools/sync-appendix-pdfs.py`; edits made here
do not flow back into the paper.
