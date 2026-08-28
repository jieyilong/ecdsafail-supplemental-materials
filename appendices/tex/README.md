# Supplemental Note sources

LaTeX sources for the three PDFs published one directory up, which the paper
cites as **Supplemental Notes A--C**. Each is a standalone document that
continues the paper's own section, figure, and table numbering, so that a
cross-reference carries the same number in the note as it does in the paper.

| Source           | Paper's name        | Published PDF                            |
| ---------------- | ------------------- | ---------------------------------------- |
| `appendix-A.tex` | Supplemental Note A | [`../detailed_results_and_circuit_improvement_trajectory.pdf`](../detailed_results_and_circuit_improvement_trajectory.pdf) |
| `appendix-B.tex` | Supplemental Note B | [`../anatomy_of_agent_identified_quantum_circuit_optimizations.pdf`](../anatomy_of_agent_identified_quantum_circuit_optimizations.pdf) |
| `appendix-C.tex` | Supplemental Note C | [`../optimization_census_of_accepted_competition_source_commits.pdf`](../optimization_census_of_accepted_competition_source_commits.pdf) |

(The `appendix-*` filenames are retained so that git history stays continuous.)

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
  needing the paper tree at build time. **Regenerate this whenever the paper is
  renumbered**, otherwise the notes silently typeset stale section and table
  numbers. Compile the paper, then re-extract each label the notes cite
  (`grep -oh '{M:[^}]*}' appendix-*.tex`) from its `main.aux`, prefixing every
  key with `M:`. References to material in a *sibling* note are written as
  literal prose ("Supplemental Note C"), not as `\Cref`, because those labels
  do not exist in the paper's `main.aux`.
- `preamble.tex`, `preamble-body.tex`, `ZZ_header.tex`, `macros.tex` — shared
  preamble, mirroring the paper's, so typography and macros match.
- `refs.bib` — bibliography database.

The content files are snapshots taken from the paper source; edits made here do
not flow back into the paper. Note that these notes are no longer part of the
paper itself — the paper links to the published PDFs by URL — so the paper is
the authority for numbering, and this directory follows it.
