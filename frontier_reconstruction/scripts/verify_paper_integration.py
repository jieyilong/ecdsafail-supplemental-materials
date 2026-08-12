#!/usr/bin/env python3
"""Verify Section 5 frontier-reconstruction claims in a compiled paper PDF."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any


PAPER_ADMITTED_IDS = (
    "b6f2b0a",
    "f1d8707",
    "39a9b5f",
    "a3b0148",
    "4352cfb",
    "1c0e0e9",
    "8e9c9a2",
    "a536a48",
)


def run_text(command: list[str]) -> str:
    completed = subprocess.run(
        command,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    return completed.stdout


def searchable_versions(text: str) -> tuple[str, str]:
    for ligature, replacement in {
        "ﬀ": "ff",
        "ﬁ": "fi",
        "ﬂ": "fl",
        "ﬃ": "ffi",
        "ﬄ": "ffl",
    }.items():
        text = text.replace(ligature, replacement)
    flat = re.sub(r"\s+", " ", text.replace("\f", "\n")).strip()
    dehyphenated = re.sub(r"(?<=[A-Za-z])-\s+(?=[a-z])", "", flat)
    return flat, dehyphenated


def contains(text: str, pattern: str) -> bool:
    return any(
        re.search(pattern, version, flags=re.IGNORECASE) is not None
        for version in searchable_versions(text)
    )


def section_window(text: str, start_pattern: str, end_pattern: str) -> str:
    start = re.search(start_pattern, text, flags=re.IGNORECASE | re.MULTILINE)
    if start is None:
        return ""
    end = re.search(
        end_pattern,
        text[start.end() :],
        flags=re.IGNORECASE | re.MULTILINE,
    )
    if end is None:
        return text[start.start() :]
    return text[start.start() : start.end() + end.start()]


def evaluate_text(text: str) -> dict[str, bool]:
    section_5 = section_window(
        text,
        r"^\s*5\s+Results and Findings",
        r"^\s*6\s+Limitations,\s*Safety",
    )
    section_5_4 = section_window(
        text,
        r"^\s*5\.4\s+Reproducibility of the Results",
        r"^\s*6\s+Limitations,\s*Safety",
    )

    return {
        "section_5_heading_present": bool(section_5),
        "section_5_4_heading_present": bool(section_5_4),
        "confirmed_cutoff_present": (
            contains(section_5, r"26 July 2026")
            and contains(section_5, r"09:21:55 UTC")
        ),
        "cutoff_submission_present": (
            contains(section_5, r"8e9c9a2")
            and contains(section_5, r"60d61859fa69")
        ),
        "snapshot_counts_present": all(
            contains(section_5_4, pattern)
            for pattern in (
                r"contains 831 rows",
                r"including 826 created by the cutoff",
                r"576 with structured Q and T metrics",
            )
        ),
        "transition_count_present": contains(
            section_5,
            r"15 manifest-selected (?:historical points|transitions)",
        ),
        "paper_admitted_ids_present": all(
            contains(section_5, short_id) for short_id in PAPER_ADMITTED_IDS
        ),
        "eight_point_figure_present": contains(
            section_5,
            r"black polyline is the eight-point archive-conditioned Pareto set",
        ),
        "artifact_reference_present": contains(
            section_5_4,
            r"(?:frontier )?reconstruction package",
        ),
        "stale_seven_point_claim_absent": not contains(
            section_5,
            r"seven[-\s]+(?:non[-\s]*)?dominated operating points|older seven-point frontier",
        ),
        "stale_cutoff_endpoint_absent": not contains(section_5_4, r"71f5115"),
        "coordination_language_absent": not contains(
            section_5,
            r"pending coauthor confirmation|pending confirmation by the coauthors|ready to paste|candidate cut",
        ),
        "wip_marker_absent": not contains(
            section_5,
            r"(?:SAMRENDRA\s+)?WIP:\s*frontier reconstruction and figure",
        ),
        "unresolved_reference_absent": "??" not in section_5,
    }


def page_count(pdf_path: Path) -> int:
    info = run_text(["pdfinfo", str(pdf_path)])
    match = re.search(r"^Pages:\s+(\d+)\s*$", info, flags=re.MULTILINE)
    if match is None:
        raise RuntimeError("pdfinfo did not report a page count")
    return int(match.group(1))


def locate_section_pages(pdf_path: Path, pages: int) -> tuple[int | None, int | None]:
    start_page = None
    end_page = None
    for page in range(1, pages + 1):
        page_text = run_text(
            ["pdftotext", "-f", str(page), "-l", str(page), str(pdf_path), "-"]
        )
        if start_page is None and "Reproducibility of the Results" in page_text:
            start_page = page
        if start_page is not None and "Limitations, Safety" in page_text:
            end_page = page
            break
    if start_page is not None and end_page is None:
        end_page = min(start_page + 2, pages)
    return start_page, end_page


def render_pages(
    pdf_path: Path,
    render_dir: Path,
    start_page: int,
    end_page: int,
) -> list[str]:
    render_dir.mkdir(parents=True, exist_ok=True)
    prefix = render_dir / "section-5-4"
    subprocess.run(
        [
            "pdftoppm",
            "-f",
            str(start_page),
            "-l",
            str(end_page),
            "-png",
            "-r",
            "180",
            str(pdf_path),
            str(prefix),
        ],
        check=True,
    )
    return [
        str(path.resolve())
        for path in sorted(render_dir.glob("section-5-4-*.png"))
    ]


def verify_pdf(pdf_path: Path, render_dir: Path | None = None) -> dict[str, Any]:
    for program in ("pdfinfo", "pdftotext"):
        if shutil.which(program) is None:
            raise RuntimeError(f"required program not found: {program}")
    if render_dir is not None and shutil.which("pdftoppm") is None:
        raise RuntimeError("required program not found: pdftoppm")

    text = run_text(["pdftotext", "-layout", str(pdf_path), "-"])
    checks = evaluate_text(text)
    urls = run_text(["pdfinfo", "-url", str(pdf_path)])
    checks["artifact_url_present"] = contains(
        urls,
        r"github\.com/jieyilong/ecdsafail-supplemental-materials/"
        r"(?:tree/main/)?frontier_reconstruction",
    )
    pages = page_count(pdf_path)
    start_page, end_page = locate_section_pages(pdf_path, pages)

    renders: list[str] = []
    if render_dir is not None and start_page is not None and end_page is not None:
        renders = render_pages(pdf_path, render_dir, start_page, end_page)

    return {
        "pdf": str(pdf_path.resolve()),
        "sha256": hashlib.sha256(pdf_path.read_bytes()).hexdigest(),
        "pages": pages,
        "section_5_4_page_start": start_page,
        "section_5_4_page_end": end_page,
        "checks": checks,
        "content_checks_passed": all(checks.values()),
        "urls_checked": True,
        "rendered_pages": renders,
        "visual_review_required": True,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pdf", required=True, type=Path)
    parser.add_argument("--render-dir", type=Path)
    parser.add_argument("--report", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.pdf.is_file():
        raise SystemExit(f"PDF not found: {args.pdf}")

    report = verify_pdf(args.pdf, args.render_dir)
    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.report is not None:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0 if report["content_checks_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
