# Low-Q circuit b6f2b0a

This directory contains a source-grounded slide deck for ECDSA.Fail submission `b6f2b0a` (source commit `e6d9fa95ab81a3414517030c974e75349912e7ca`).

The analysis uses an isolated restoration at:

`/Users/jieyilong/Personal/research/ShorOptimization/shor_optimization_workspace/ecdsafail-b6f2b0a-analysis`

The circuit is the low-qubit TrailMix route built around a register-shared, shrunken Proos--Zalka-style extended Euclidean algorithm. It is not the dialog-GCD architecture used by the product-score track.

Structural count-only instrumentation reproduced the submitted metrics:

- Peak logical width: 825 qubits
- Structural Toffoli count: 489,161,900
- Product: 403,558,567,500
- Peak phases: `ec3.inv_fwd` and `ec3.alt.cancel`

The deck distinguishes the accumulated low-qubit architecture from the submission-specific Q825 change: removal of the eighth persistent quotient-length lane using an implicit high-bit reconstruction and an eight-scratch split-five kernel. It also explains the Shrunken-PZ lineage and underlying extended-Euclidean inversion algorithm, and documents the exact 825-qubit live set, the register-shared EEA layout and fixed schedule, the three inherited Q826 hosting windows, dynamic cursor reconstruction, measurement-based release and recomputation, and the alternate-witness cancellation pass.

## Verification notes

- The release builder completed with count-only phase instrumentation and reproduced `Q=825` and `T=489161900` exactly.
- The 25-page PDF compiles without overfull-box or undefined-reference warnings and was rendered page by page for visual inspection.
- The historical source snapshot's complete Rust test target does not currently compile because unrelated test-only modules reference missing experimental helpers and obsolete simulator methods. This does not affect the successful release build or the structural count used in the deck.
