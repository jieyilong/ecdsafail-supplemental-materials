from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from verify_paper_integration import evaluate_text


CURRENT_SECTION_5 = """
5 Results and Findings

Solutions on the Pareto frontier. Teal circles and orange diamonds show the
15 manifest-selected historical points. The thick black line and filled circles
mark the admitted nondominated operating points at the cutoff, and the table
lists the eight admitted Pareto points at the cutoff.

b6f2b0a f1d8707 39a9b5f a3b0148 4352cfb 1c0e0e9 8e9c9a2 a536a48
The data cutoff is 26 July 2026, 09:21:55 UTC. The promoted source commit is
60d61859fa69.

5.5 Reproducibility of the Results

The frozen response contains 831 rows, including 826 created by the cutoff and
576 with structured Q and T metrics. The historical display contains 15
manifest-selected transitions. The reconstruction package is available at
https://github.com/jieyilong/ecdsafail-supplemental-materials/tree/main/frontier_reconstruction.

6 Limitations, Safety, and Responsible Framing
"""

TABLE_OF_CONTENTS = """
5 Results and Findings ............................................. 32
    5.5 Reproducibility of the Results ............................. 60
6 Limitations, Safety, and Responsible Framing ..................... 61
"""


class PaperIntegrationVerifierTest(unittest.TestCase):
    def test_accepts_current_section_5_claims(self) -> None:
        checks = evaluate_text(CURRENT_SECTION_5)
        self.assertTrue(all(checks.values()), checks)

    def test_accepts_renumbered_reproducibility_subsection(self) -> None:
        text = CURRENT_SECTION_5.replace(
            "5.5 Reproducibility of the Results",
            "5.4 Reproducibility of the Results",
        )
        checks = evaluate_text(text)
        self.assertTrue(all(checks.values()), checks)

    def test_ignores_table_of_contents_entries(self) -> None:
        checks = evaluate_text(TABLE_OF_CONTENTS + "\f" + CURRENT_SECTION_5)
        self.assertTrue(all(checks.values()), checks)

    def test_rejects_old_cutoff_and_missing_artifact(self) -> None:
        text = CURRENT_SECTION_5.replace(
            "The reconstruction package is available at\n"
            "https://github.com/jieyilong/ecdsafail-supplemental-materials/"
            "tree/main/frontier_reconstruction.",
            "The older seven-point frontier ends at 71f5115.",
        )
        checks = evaluate_text(text)
        self.assertFalse(checks["artifact_reference_present"])
        self.assertFalse(checks["stale_seven_point_claim_absent"])
        self.assertFalse(checks["stale_cutoff_endpoint_absent"])

    def test_rejects_snapshot_count_drift(self) -> None:
        text = CURRENT_SECTION_5.replace("contains 831 rows", "contains 830 rows")
        checks = evaluate_text(text)
        self.assertFalse(checks["snapshot_counts_present"])

    def test_accepts_admitted_table_floated_above_section_heading(self) -> None:
        """The admitted-Pareto table is a float. When LaTeX places it at the top
        of the page carrying the Section 5 heading, its rows are extracted
        before that heading and so fall outside the Section 5 window."""
        floated = CURRENT_SECTION_5.replace(
            "b6f2b0a f1d8707 39a9b5f a3b0148 4352cfb 1c0e0e9 8e9c9a2 a536a48\n", ""
        )
        text = (
            "b6f2b0a f1d8707 39a9b5f a3b0148 4352cfb 1c0e0e9 8e9c9a2 a536a48\n"
            + floated
        )
        checks = evaluate_text(text)
        self.assertTrue(checks["paper_admitted_ids_present"], checks)

    def test_accepts_reworded_frontier_caption(self) -> None:
        """The check must survive rewording of the figure caption, so long as
        the paper still asserts an eight-point Pareto set."""
        text = CURRENT_SECTION_5.replace(
            "the table\nlists the eight admitted Pareto points at the cutoff.",
            "the frontier holds eight admitted Pareto operating points.",
        )
        checks = evaluate_text(text)
        self.assertTrue(checks["eight_point_figure_present"], checks)

    def test_rejects_missing_paper_admitted_point(self) -> None:
        text = CURRENT_SECTION_5.replace(" a536a48", "")
        checks = evaluate_text(text)
        self.assertFalse(checks["paper_admitted_ids_present"])


if __name__ == "__main__":
    unittest.main()
