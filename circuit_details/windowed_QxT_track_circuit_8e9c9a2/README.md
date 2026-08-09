# Window-Compatible 8e9c9a2 Circuit

This directory documents the runtime-table, coherently addressed adaptation of ECDSA.Fail submission `8e9c9a2`.

- `windowed_QxT_track_circuit_8e9c9a2_details.tex` contains the technical note source.
- `windowed_QxT_track_circuit_8e9c9a2_details.pdf` is the compiled technical note.
- `paired_100k_counts.tsv` records the compact results of the independently seeded, paired 100,000-input comparison.

The implementation is maintained on branch `codex/windowed-8e9c9a2` of `jieyilong/ecdsafail-challenge`. The note records the runtime table ABI, QROM construction, coherent identity handling, exact payload replay, circuit-to-source correspondence, measured resources, resumable evaluation procedure, and validation scope.
