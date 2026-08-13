#!/usr/bin/env python3
"""Rebuild the paper's frozen frontier evidence package from pinned inputs."""

from __future__ import annotations

import argparse
import csv
import hashlib
import html
import json
import math
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "data" / "curation" / "reconstruction-50pct.json"
DEFAULT_OUTPUT = ROOT / "output"

INK = "#1F2933"
MUTED = "#68737D"
GRID = "#D9DEE3"
PAPER = "#FFFFFF"
PANEL = "#F7F8F9"
PRODUCT = "#007C78"
LOW_Q = "#D55E00"
SENSITIVITY = "#0072B2"


@dataclass(frozen=True)
class Submission:
    short_id: str
    submission_id: str
    solver: str
    status: str
    promotion_status: str | None
    q: int
    t: int
    score: int
    source_commit: str | None
    submission_commit: str | None
    created_at: str
    updated_at: str | None
    note: str

    @property
    def created_dt(self) -> datetime:
        return parse_iso(self.created_at)

    @property
    def updated_dt(self) -> datetime:
        return parse_iso(self.updated_at or self.created_at)

    @property
    def is_promoted(self) -> bool:
        return self.promotion_status == "promoted"


def parse_iso(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def resolve_path(config_path: Path, relative: str) -> Path:
    return config_path.parents[2] / relative


def source_commit(raw: dict[str, Any]) -> str | None:
    if raw.get("promotionStatus") == "promoted":
        return raw.get("promotedSourceRef") or raw.get("submissionCommitSha")
    return raw.get("submissionCommitSha") or raw.get("promotedSourceRef")


def normalize_submissions(raw_payload: dict[str, Any]) -> list[Submission]:
    rows: list[Submission] = []
    for raw in raw_payload.get("submissions", []):
        metrics = raw.get("officialMetrics") or {}
        q, t = metrics.get("qubits"), metrics.get("toffoli")
        if not q or not t:
            continue
        score = raw.get("officialScore") or int(q) * int(t)
        rows.append(
            Submission(
                short_id=(raw.get("id") or "")[:7],
                submission_id=raw.get("id") or "",
                solver=raw.get("solverUsername") or "",
                status=raw.get("status") or "",
                promotion_status=raw.get("promotionStatus"),
                q=int(q),
                t=int(t),
                score=int(score),
                source_commit=source_commit(raw),
                submission_commit=raw.get("submissionCommitSha"),
                created_at=raw.get("createdAt") or "",
                updated_at=raw.get("updatedAt"),
                note=raw.get("note") or "",
            )
        )
    return rows


def compare_api_checkpoint(
    checkpoint_rows: list[dict[str, Any]],
    current_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    """Compare the tracked June checkpoint with the pinned July response."""
    current_by_id = {row["id"]: row for row in current_rows}
    mappings = {
        "solver": "solverUsername",
        "status": "status",
        "promotion_status": "promotionStatus",
        "official_score": "officialScore",
        "improved": "improved",
        "rejection_reason": "rejectionReason",
        "source_ref": "promotedSourceRef",
        "commit_sha": "submissionCommitSha",
        "claimed_score": "claimedScore",
        "created": "createdAt",
        "updated": "updatedAt",
    }
    missing_ids: list[str] = []
    changed_rows: list[dict[str, Any]] = []
    for checkpoint in checkpoint_rows:
        current = current_by_id.get(checkpoint["id"])
        if current is None:
            missing_ids.append(checkpoint["id"])
            continue
        differences: dict[str, dict[str, Any]] = {}
        for checkpoint_key, current_key in mappings.items():
            if checkpoint.get(checkpoint_key) != current.get(current_key):
                differences[checkpoint_key] = {
                    "checkpoint": checkpoint.get(checkpoint_key),
                    "pinned_response": current.get(current_key),
                }
        checkpoint_metrics = (checkpoint.get("qubits"), checkpoint.get("toffoli"))
        current_metrics_raw = current.get("officialMetrics") or {}
        current_metrics = (current_metrics_raw.get("qubits"), current_metrics_raw.get("toffoli"))
        if checkpoint_metrics != current_metrics:
            differences["official_metrics"] = {
                "checkpoint": list(checkpoint_metrics),
                "pinned_response": list(current_metrics),
            }
        if differences:
            changed_rows.append(
                {
                    "submission": checkpoint["id"][:7],
                    "full_id": checkpoint["id"],
                    "differences": differences,
                }
            )
    return {
        "checkpoint_rows": len(checkpoint_rows),
        "retained_in_pinned_response": len(checkpoint_rows) - len(missing_ids),
        "missing_ids": missing_ids,
        "unchanged_common_field_rows": len(checkpoint_rows) - len(missing_ids) - len(changed_rows),
        "changed_rows": changed_rows,
        "supports_retention_but_not_exhaustiveness": True,
    }


def note_validation_evidence(note: str) -> tuple[bool, str]:
    """Recognize explicit complete-run, three-channel zero-failure statements."""
    markdown_neutral = re.sub(r"[`*_]", "", note.lower())
    numeric_normalized = re.sub(r"(?<=\d),(?=\d)", "", markdown_neutral)
    compact = re.sub(r"\s+", " ", numeric_normalized).strip()
    has_9024 = bool(re.search(r"\b9024\b", compact))
    triplet = bool(
        re.search(
            r"(?:cls|classical(?:-output)?)\s*/\s*"
            r"(?:pha|phase(?:-garbage)?)\s*/\s*"
            r"(?:anc|ancilla(?:-garbage)?)"
            r"(?:\s+(?:failures?|mismatches?|batches))?\s*"
            r"(?:[:=]\s*)?0\s*/\s*0\s*/\s*0\b",
            compact,
        )
    )
    coordinated_zero_list = bool(
        re.search(
            r"\bzero\s+classical(?:-output)?(?:\s+(?:failures?|mismatches?))?\s*"
            r"(?:,|and|or)\s*phase(?:-garbage)?(?:\s+(?:failures?|batches))?\s*"
            r"(?:,|and|or)\s*(?:and\s+|or\s+)?ancilla(?:-garbage)?"
            r"(?:\s+(?:failures?|batches))?\b",
            compact,
        )
    )

    def dimension_zero(label: str) -> bool:
        outcome = r"(?:failures?|mismatches?|batches|errors?)"
        return bool(
            re.search(rf"\b(?:zero|0)\b\s+{label}(?:\s+{outcome})?", compact)
            or re.search(
                rf"{label}(?:\s+{outcome})?\s*(?::|=|\bis\b|\bwas\b|\bwere\b)?\s*"
                rf"\b(?:zero|0)\b",
                compact,
            )
        )

    separate_zeroes = all(
        dimension_zero(label)
        for label in ("classical(?:-output)?", "phase(?:-garbage)?", "ancilla(?:-garbage)?")
    )
    # "All shots OK" is deliberately insufficient: the public prose must name
    # all three evaluator channels and record zero failures in each.
    passes = has_9024 and (triplet or coordinated_zero_list or separate_zeroes)

    evidence_lines = []
    for line in note.splitlines():
        normalized = line.strip()
        lowered = re.sub(r"[`*_]", "", normalized.lower())
        if normalized and (
            "9024" in lowered
            or "9,024" in lowered
            or (
                any(k in lowered for k in ("classical", "phase", "ancilla"))
                and bool(re.search(r"\b(?:zero|0)\b", lowered))
            )
            or re.search(r"0\s*/\s*0\s*/\s*0", lowered)
        ):
            evidence_lines.append(normalized)
    excerpt = " | ".join(evidence_lines[:4])[:700]
    return passes, excerpt


def deduplicate_coordinates(rows: Iterable[Submission]) -> list[Submission]:
    selected: dict[tuple[int, int], Submission] = {}
    for row in sorted(rows, key=lambda item: (item.created_dt, item.short_id)):
        selected.setdefault((row.q, row.t), row)
    return list(selected.values())


def pareto(rows: Iterable[Submission]) -> list[Submission]:
    points = sorted(deduplicate_coordinates(rows), key=lambda item: (item.q, item.t, item.created_dt))
    frontier: list[Submission] = []
    best_t = math.inf
    for point in points:
        if point.t < best_t:
            frontier.append(point)
            best_t = point.t
    return frontier


def row_dict(row: Submission, *, note_evidence: bool | None = None, excerpt: str = "") -> dict[str, Any]:
    result: dict[str, Any] = {
        "submission": row.short_id,
        "submission_uuid": row.submission_id,
        "source_commit": row.source_commit,
        "submission_commit": row.submission_commit,
        "solver": row.solver,
        "api_status": row.status,
        "promotion_status": row.promotion_status or "",
        "q": row.q,
        "t": row.t,
        "qt": row.score,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }
    if note_evidence is not None:
        result["note_validation_evidence"] = note_evidence
        result["note_evidence_excerpt"] = excerpt
    return result


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        raise ValueError(f"refusing to write empty CSV: {path}")
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=list(rows[0].keys()),
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(rows)


def reconcile_ledger(path: Path, submissions: list[Submission]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    by_id = {row.short_id: row for row in submissions}
    reconciled: list[dict[str, Any]] = []
    unresolved: list[str] = []
    repaired_ids: list[dict[str, str]] = []
    commit_mismatches: list[dict[str, str | None]] = []

    with path.open(newline="", encoding="utf-8-sig") as handle:
        ledger_rows = list(csv.DictReader(handle))

    for source in ledger_rows:
        raw_id = (source.get("submission") or "").lower()
        match = by_id.get(raw_id)
        resolution = "exact_id"
        if match is None:
            q, t = int(source["qubits"]), int(source["toffoli"])
            candidates = [
                row
                for row in submissions
                if row.q == q and row.t == t and row.solver.lower() == source["solver"].lower()
            ]
            if len(candidates) == 1:
                match = candidates[0]
                resolution = "recovered_from_solver_q_t"
                repaired_ids.append({"published": raw_id, "official": match.short_id})
            else:
                unresolved.append(raw_id)

        official_id = match.short_id if match else ""
        official_commit = match.source_commit if match else None
        raw_commit = source.get("commit") or ""
        commit_matches = bool(official_commit and raw_commit and official_commit.startswith(raw_commit.lower()))
        if match and not commit_matches:
            commit_mismatches.append(
                {
                    "submission": official_id,
                    "published_commit": raw_commit,
                    "official_commit": official_commit,
                }
            )

        reconciled.append(
            {
                "published_submission": raw_id,
                "official_submission": official_id,
                "id_resolution": resolution if match else "unresolved",
                "published_commit": raw_commit,
                "official_source_commit": official_commit or "",
                "commit_matches": commit_matches,
                "solver": source.get("solver") or "",
                "created": source.get("created") or "",
                "q": source.get("qubits") or "",
                "t": source.get("toffoli") or "",
                "publication_bucket": source.get("publication_bucket") or "",
                "source_state": source.get("source_state") or "",
                "mechanism_families": source.get("mechanism_families") or "",
                "selection_warning": "spreadsheet_id_or_commit_repaired" if resolution != "exact_id" else "",
            }
        )

    return reconciled, {
        "rows": len(ledger_rows),
        "unresolved_ids": unresolved,
        "repaired_ids": repaired_ids,
        "commit_mismatches": commit_mismatches,
    }


class Scene:
    def __init__(self, width: int = 1200, height: int = 640) -> None:
        self.width = width
        self.height = height
        self.commands: list[dict[str, Any]] = []

    def line(self, x1: float, y1: float, x2: float, y2: float, color: str, width: float = 1, dash: str | None = None) -> None:
        self.commands.append({"kind": "line", "x1": x1, "y1": y1, "x2": x2, "y2": y2, "color": color, "width": width, "dash": dash})

    def polyline(self, points: list[tuple[float, float]], color: str, width: float = 2, dash: str | None = None) -> None:
        self.commands.append({"kind": "polyline", "points": points, "color": color, "width": width, "dash": dash})

    def circle(self, x: float, y: float, radius: float, stroke: str, fill: str, width: float = 1.5) -> None:
        self.commands.append({"kind": "circle", "x": x, "y": y, "radius": radius, "stroke": stroke, "fill": fill, "width": width})

    def diamond(self, x: float, y: float, radius: float, stroke: str, fill: str, width: float = 1.5) -> None:
        points = [(x, y - radius), (x + radius, y), (x, y + radius), (x - radius, y)]
        self.commands.append({"kind": "polygon", "points": points, "stroke": stroke, "fill": fill, "width": width})

    def rect(self, x: float, y: float, width: float, height: float, stroke: str, fill: str, line_width: float = 1) -> None:
        self.commands.append({"kind": "rect", "x": x, "y": y, "w": width, "h": height, "stroke": stroke, "fill": fill, "width": line_width})

    def text(self, x: float, y: float, value: str, size: float = 12, color: str = INK, anchor: str = "start", bold: bool = False) -> None:
        self.commands.append({"kind": "text", "x": x, "y": y, "value": value, "size": size, "color": color, "anchor": anchor, "bold": bold})


def scaled(value: float, low: float, high: float, start: float, end: float) -> float:
    if high == low:
        return (start + end) / 2
    return start + (value - low) * (end - start) / (high - low)


def plot_frame(
    scene: Scene,
    box: tuple[float, float, float, float],
    x_bounds: tuple[float, float],
    y_bounds: tuple[float, float],
    x_ticks: list[float],
    y_ticks: list[float],
    *,
    log_y: bool,
    y_labels: list[str],
    tick_size: float = 9,
    axis_size: float = 10,
) -> tuple[Any, Any]:
    left, top, width, height = box
    scene.rect(left, top, width, height, GRID, PANEL, 1)

    def px(q: float) -> float:
        return scaled(q, x_bounds[0], x_bounds[1], left, left + width)

    def py(t: float) -> float:
        value = math.log10(t) if log_y else t
        low = math.log10(y_bounds[0]) if log_y else y_bounds[0]
        high = math.log10(y_bounds[1]) if log_y else y_bounds[1]
        return scaled(value, low, high, top + height, top)

    for tick in x_ticks:
        x = px(tick)
        scene.line(x, top, x, top + height, GRID, 0.8)
        scene.text(x, top + height + axis_size + 6, f"{int(tick):,}", tick_size, MUTED, "middle")
    for tick, label in zip(y_ticks, y_labels, strict=True):
        y = py(tick)
        scene.line(left, y, left + width, y, GRID, 0.8)
        scene.text(left - 5, y + tick_size / 3, label, tick_size, MUTED, "end")
    scene.text(left + width / 2, top + height + axis_size + 18, "Peak logical qubits (Q)", axis_size, INK, "middle", True)
    return px, py


def build_paper_scene(
    transition_rows: list[Submission],
    primary_pareto: list[Submission],
    figure_config: dict[str, Any],
) -> Scene:
    # The PDF canvas matches the approximate LLNCS text width. Text therefore
    # stays at publication size when LaTeX inserts it at \linewidth.
    scene = Scene(width=360, height=255)
    scene.rect(0, 0, scene.width, scene.height, PAPER, PAPER, 0)
    scene.text(
        36,
        15,
        figure_config.get("paper_title", "Retrospective frontier reconstruction"),
        10.5,
        INK,
        "start",
        True,
    )
    scene.text(
        36,
        27,
        figure_config.get(
            "paper_subtitle",
            f"{len(transition_rows)} selected transitions; {len(primary_pareto)} primary-policy points",
        ),
        6.5,
        MUTED,
    )

    main_box = (36, 43, 306, 148)
    px, py = plot_frame(
        scene,
        main_box,
        (800, 2800),
        (1_000_000, 600_000_000),
        [800, 1200, 1600, 2000, 2400, 2800],
        [1_000_000, 10_000_000, 100_000_000],
        log_y=True,
        y_labels=["1M", "10M", "100M"],
        tick_size=6.2,
        axis_size=7.2,
    )
    scene.text(36, 38, "Average executed Toffoli (log scale)", 6.5, MUTED, "start", True)

    product_rows = [row for row in transition_rows if getattr(row, "track", None) == "product"]
    low_q_rows = [row for row in transition_rows if getattr(row, "track", None) == "low_q"]
    scene.polyline([(px(row.q), py(row.t)) for row in product_rows], PRODUCT, 1.4)
    scene.polyline([(px(row.q), py(row.t)) for row in low_q_rows], LOW_Q, 1.4)
    scene.polyline([(px(row.q), py(row.t)) for row in primary_pareto], INK, 1.2, "3 2")

    for row in product_rows:
        x, y = px(row.q), py(row.t)
        scene.circle(x, y, 2.2, PRODUCT, PAPER, 1.1)
    for row in low_q_rows:
        x, y = px(row.q), py(row.t)
        scene.diamond(x, y, 2.7, LOW_Q, PAPER, 1.1)
    for row in primary_pareto:
        scene.circle(px(row.q), py(row.t), 1.35, INK, INK, 0.8)

    anchors = {
        "30c8ded": (-3, -5, "end", PRODUCT),
        "71f5115": (3, 9, "start", PRODUCT),
        "8e9c9a2": (3, 9, "start", PRODUCT),
        "b6f2b0a": (3, 18, "start", LOW_Q),
        "39a9b5f": (18, 2, "start", LOW_Q),
    }
    transition_by_id = {row.short_id: row for row in transition_rows}
    if "8e9c9a2" in transition_by_id:
        anchors.pop("71f5115")
    for short_id, (dx, dy, anchor, color) in anchors.items():
        row = transition_by_id.get(short_id)
        if row is None:
            continue
        scene.text(px(row.q) + dx, py(row.t) + dy, short_id, 5.8, color, anchor, True)

    legend_y = 226
    scene.line(38, legend_y, 51, legend_y, PRODUCT, 1.4)
    scene.circle(44.5, legend_y, 2, PRODUCT, PAPER, 1)
    scene.text(55, legend_y + 2, "product milestones", 6.2, INK)
    scene.line(135, legend_y, 148, legend_y, LOW_Q, 1.4)
    scene.diamond(141.5, legend_y, 2.4, LOW_Q, PAPER, 1)
    scene.text(152, legend_y + 2, "low-Q foreground", 6.2, INK)
    scene.line(235, legend_y, 248, legend_y, INK, 1.2, "3 2")
    scene.text(
        252,
        legend_y + 2,
        figure_config.get("paper_primary_label", "API-metric Pareto"),
        6.2,
        INK,
    )
    scene.text(
        36,
        247,
        figure_config.get(
            "paper_footer",
            "Population: pinned-response rows at the data cutoff; no exhaustive-history claim.",
        ),
        6.2,
        MUTED,
    )
    return scene


def build_sensitivity_scene(
    official: list[Submission],
    note_rule: list[Submission],
    paper_admitted: list[Submission],
    figure_config: dict[str, Any],
) -> Scene:
    scene = Scene()
    scene.rect(0, 0, scene.width, scene.height, PAPER, PAPER, 0)
    scene.text(
        58,
        35,
        figure_config.get("sensitivity_title", "Inclusion-rule sensitivity at the data cutoff"),
        22,
        INK,
        "start",
        True,
    )
    scene.text(
        58,
        57,
        "API metrics, explicit note evidence, and the paper's curated selection produce different sets.",
        11,
        MUTED,
    )
    box = (78, 105, 735, 410)
    px, py = plot_frame(
        scene,
        box,
        (800, 1200),
        (1_000_000, 600_000_000),
        [800, 900, 1000, 1100, 1200],
        [1_000_000, 10_000_000, 100_000_000],
        log_y=True,
        y_labels=["1M", "10M", "100M"],
    )
    scene.text(78, 92, "A  |  Pareto sets under three admission rules", 12, INK, "start", True)
    scene.polyline([(px(row.q), py(row.t)) for row in paper_admitted], MUTED, 2, "6 5")
    scene.polyline([(px(row.q), py(row.t)) for row in note_rule], LOW_Q, 2, "3 4")
    scene.polyline([(px(row.q), py(row.t)) for row in official], SENSITIVITY, 2.4)
    scene.line(160, 132, 184, 132, MUTED, 2, "6 5")
    scene.text(192, 136, f"paper admitted {len(paper_admitted)}", 8.8, MUTED)
    scene.line(272, 132, 296, 132, LOW_Q, 2, "3 4")
    scene.text(304, 136, f"note rule {len(note_rule)}", 8.8, LOW_Q)
    scene.line(406, 132, 430, 132, SENSITIVITY, 2.4)
    scene.text(438, 136, f"API metrics {len(official)}", 8.8, SENSITIVITY)
    for row in paper_admitted:
        scene.circle(px(row.q), py(row.t), 4.1, MUTED, PAPER, 1.6)
    for row in note_rule:
        scene.circle(px(row.q), py(row.t), 3.2, LOW_Q, PAPER, 1.5)
    for row in official:
        scene.circle(px(row.q), py(row.t), 2.7, SENSITIVITY, SENSITIVITY, 1)

    official_ids = {row.short_id for row in official}
    note_ids = {row.short_id for row in note_rule}
    paper_ids = {row.short_id for row in paper_admitted}
    official_only_vs_note = [row.short_id for row in official if row.short_id not in note_ids]
    note_only_vs_official = [row.short_id for row in note_rule if row.short_id not in official_ids]
    official_only_vs_paper = [row.short_id for row in official if row.short_id not in paper_ids]
    paper_only_vs_official = [row.short_id for row in paper_admitted if row.short_id not in official_ids]

    scene.text(855, 104, "B  |  What changes", 12, INK, "start", True)
    scene.text(855, 135, "API-metric rows", 10.5, SENSITIVITY, "start", True)
    scene.text(855, 153, f"{len(official)} points from metric-bearing rows in the declared population.", 9.4, INK)
    scene.text(855, 170, "Structured API metrics; no validator-clean inference.", 9.2, MUTED)

    scene.text(855, 210, "Public-note parser", 10.5, LOW_Q, "start", True)
    scene.text(855, 228, f"{len(note_rule)} points; prose format changes admission.", 9.4, INK)
    scene.text(855, 250, "API-only: " + ", ".join(official_only_vs_note), 8.7, MUTED)
    scene.text(855, 268, "Note-only after re-frontiering: " + ", ".join(note_only_vs_official), 8.7, MUTED)

    scene.text(855, 310, "Paper-admitted set", 10.5, MUTED, "start", True)
    scene.text(855, 328, f"{len(paper_admitted)} points under the paper's curated admission rule.", 9.4, INK)
    scene.text(855, 350, f"Pinned-response frontier adds {len(official_only_vs_paper)} IDs.", 8.9, MUTED)
    scene.text(855, 368, "Paper-only after re-frontiering: " + ", ".join(paper_only_vs_official), 8.7, MUTED)

    scene.text(855, 420, "Interpretation", 10.5, INK, "start", True)
    scene.text(855, 440, "Main figure uses the paper-admitted set.", 9.4, MUTED)
    scene.text(855, 457, "Other sets are sensitivity analyses, not alternate headline results.", 9.4, MUTED)
    scene.text(
        58,
        618,
        "Reviewer audit figure. No set is promoted to validator-clean status by API metrics alone.",
        9,
        MUTED,
    )
    return scene


def render_svg(scene: Scene, path: Path) -> None:
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{scene.width}" height="{scene.height}" viewBox="0 0 {scene.width} {scene.height}">',
        '<rect width="100%" height="100%" fill="#FFFFFF"/>',
    ]
    for command in scene.commands:
        kind = command["kind"]
        dash = f' stroke-dasharray="{command["dash"]}"' if command.get("dash") else ""
        if kind == "line":
            parts.append(f'<line x1="{command["x1"]:.2f}" y1="{command["y1"]:.2f}" x2="{command["x2"]:.2f}" y2="{command["y2"]:.2f}" stroke="{command["color"]}" stroke-width="{command["width"]}"{dash}/>')
        elif kind == "polyline":
            points = " ".join(f"{x:.2f},{y:.2f}" for x, y in command["points"])
            parts.append(f'<polyline points="{points}" fill="none" stroke="{command["color"]}" stroke-width="{command["width"]}" stroke-linejoin="round" stroke-linecap="round"{dash}/>')
        elif kind == "circle":
            parts.append(f'<circle cx="{command["x"]:.2f}" cy="{command["y"]:.2f}" r="{command["radius"]}" stroke="{command["stroke"]}" fill="{command["fill"]}" stroke-width="{command["width"]}"/>')
        elif kind == "polygon":
            points = " ".join(f"{x:.2f},{y:.2f}" for x, y in command["points"])
            parts.append(f'<polygon points="{points}" stroke="{command["stroke"]}" fill="{command["fill"]}" stroke-width="{command["width"]}"/>')
        elif kind == "rect":
            parts.append(f'<rect x="{command["x"]:.2f}" y="{command["y"]:.2f}" width="{command["w"]:.2f}" height="{command["h"]:.2f}" stroke="{command["stroke"]}" fill="{command["fill"]}" stroke-width="{command["width"]}"/>')
        elif kind == "text":
            weight = "700" if command["bold"] else "400"
            parts.append(f'<text x="{command["x"]:.2f}" y="{command["y"]:.2f}" fill="{command["color"]}" font-family="Arial, Helvetica, sans-serif" font-size="{command["size"]}" font-weight="{weight}" text-anchor="{command["anchor"]}">{html.escape(command["value"])}</text>')
    parts.append("</svg>\n")
    path.write_text("\n".join(parts), encoding="utf-8")


def render_pdf(scene: Scene, path: Path) -> bool:
    try:
        from reportlab.lib.colors import HexColor
        from reportlab.pdfbase.pdfmetrics import stringWidth
        from reportlab.pdfgen import canvas
    except ImportError:
        return False
    pdf = canvas.Canvas(str(path), pagesize=(scene.width, scene.height), invariant=1)
    for command in scene.commands:
        kind = command["kind"]
        if kind in {"line", "polyline"}:
            pdf.setStrokeColor(HexColor(command["color"]))
            pdf.setLineWidth(command["width"])
            if command.get("dash"):
                pdf.setDash(*[float(value) for value in command["dash"].split()])
            else:
                pdf.setDash()
            if kind == "line":
                pdf.line(command["x1"], scene.height - command["y1"], command["x2"], scene.height - command["y2"])
            else:
                points = command["points"]
                path_obj = pdf.beginPath()
                path_obj.moveTo(points[0][0], scene.height - points[0][1])
                for x, y in points[1:]:
                    path_obj.lineTo(x, scene.height - y)
                pdf.drawPath(path_obj, stroke=1, fill=0)
        elif kind == "circle":
            pdf.setStrokeColor(HexColor(command["stroke"]))
            pdf.setFillColor(HexColor(command["fill"]))
            pdf.setLineWidth(command["width"])
            pdf.circle(command["x"], scene.height - command["y"], command["radius"], stroke=1, fill=1)
        elif kind == "polygon":
            pdf.setStrokeColor(HexColor(command["stroke"]))
            pdf.setFillColor(HexColor(command["fill"]))
            pdf.setLineWidth(command["width"])
            path_obj = pdf.beginPath()
            path_obj.moveTo(command["points"][0][0], scene.height - command["points"][0][1])
            for x, y in command["points"][1:]:
                path_obj.lineTo(x, scene.height - y)
            path_obj.close()
            pdf.drawPath(path_obj, stroke=1, fill=1)
        elif kind == "rect":
            pdf.setStrokeColor(HexColor(command["stroke"]))
            pdf.setFillColor(HexColor(command["fill"]))
            pdf.setLineWidth(command["width"])
            pdf.rect(command["x"], scene.height - command["y"] - command["h"], command["w"], command["h"], stroke=1, fill=1)
        elif kind == "text":
            font = "Helvetica-Bold" if command["bold"] else "Helvetica"
            pdf.setFont(font, command["size"])
            pdf.setFillColor(HexColor(command["color"]))
            width = stringWidth(command["value"], font, command["size"])
            x = command["x"]
            if command["anchor"] == "middle":
                x -= width / 2
            elif command["anchor"] == "end":
                x -= width
            pdf.drawString(x, scene.height - command["y"], command["value"])
    pdf.showPage()
    pdf.save()
    return True


def render_png(scene: Scene, path: Path, scale_factor: int = 2) -> bool:
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        return False
    image = Image.new("RGB", (scene.width * scale_factor, scene.height * scale_factor), PAPER)
    draw = ImageDraw.Draw(image)
    regular_path = Path("/System/Library/Fonts/Supplemental/Arial.ttf")
    bold_path = Path("/System/Library/Fonts/Supplemental/Arial Bold.ttf")
    fonts: dict[tuple[int, bool], Any] = {}

    def font(size: float, bold: bool) -> Any:
        key = (round(size * scale_factor), bold)
        if key not in fonts:
            selected = bold_path if bold and bold_path.exists() else regular_path
            fonts[key] = ImageFont.truetype(str(selected), key[0]) if selected.exists() else ImageFont.load_default()
        return fonts[key]

    def point(x: float, y: float) -> tuple[int, int]:
        return round(x * scale_factor), round(y * scale_factor)

    for command in scene.commands:
        kind = command["kind"]
        width = max(1, round(command.get("width", 1) * scale_factor))
        if kind == "line":
            draw.line([point(command["x1"], command["y1"]), point(command["x2"], command["y2"])], fill=command["color"], width=width)
        elif kind == "polyline":
            draw.line([point(x, y) for x, y in command["points"]], fill=command["color"], width=width, joint="curve")
        elif kind == "circle":
            x, y, radius = command["x"], command["y"], command["radius"]
            draw.ellipse([point(x - radius, y - radius), point(x + radius, y + radius)], fill=command["fill"], outline=command["stroke"], width=width)
        elif kind == "polygon":
            draw.polygon([point(x, y) for x, y in command["points"]], fill=command["fill"], outline=command["stroke"])
        elif kind == "rect":
            draw.rectangle([point(command["x"], command["y"]), point(command["x"] + command["w"], command["y"] + command["h"])], fill=command["fill"], outline=command["stroke"], width=width)
        elif kind == "text":
            used_font = font(command["size"], command["bold"])
            anchor = {"start": "ls", "middle": "ms", "end": "rs"}[command["anchor"]]
            draw.text(point(command["x"], command["y"]), command["value"], fill=command["color"], font=used_font, anchor=anchor)
    image.save(path, format="PNG", optimize=True)
    return True


def attach_tracks(rows: list[Submission], config: dict[str, Any]) -> list[Submission]:
    """Attach an ephemeral track attribute while preserving the Submission API."""
    by_id = {row.short_id: row for row in rows}
    result = []
    for selected in config["transition_slice"]:
        row = by_id[selected["id"]]
        object.__setattr__(row, "track", selected["track"])
        result.append(row)
    return result


def verify_data_cutoff(
    config: dict[str, Any],
    submissions: list[Submission],
    data_cutoff_dt: datetime,
) -> dict[str, Any] | None:
    cutoff = config.get("data_cutoff")
    if not cutoff:
        return None

    threshold = int(cutoff["threshold_score"])
    promoted = sorted(
        (row for row in submissions if row.is_promoted),
        key=lambda row: (row.created_dt, row.short_id),
    )
    first_crossing = next((row for row in promoted if row.score <= threshold), None)
    if first_crossing is None:
        raise SystemExit("the pinned response contains no promoted row crossing the 50% threshold")
    if first_crossing.short_id != cutoff["submission_id"]:
        raise SystemExit(
            "configured data cutoff is not the first promoted threshold crossing: "
            f"expected {cutoff['submission_id']}, got {first_crossing.short_id}"
        )
    if first_crossing.source_commit != cutoff["source_commit"]:
        raise SystemExit("configured data-cutoff source commit does not match the API")
    if first_crossing.updated_dt > data_cutoff_dt:
        raise SystemExit("data cutoff precedes the crossing submission's final API update")

    earlier = [row for row in promoted if row.created_dt < first_crossing.created_dt]
    best_earlier = min(earlier, key=lambda row: (row.score, row.created_dt, row.short_id))
    if best_earlier.score <= threshold:
        raise SystemExit("a promoted row before the configured cutoff already crossed the threshold")

    return {
        **cutoff,
        "first_crossing_verified": True,
        "cutoff_metrics": row_dict(first_crossing),
        "best_promoted_score_before_crossing": best_earlier.score,
        "margin_below_threshold": threshold - first_crossing.score,
        "data_cutoff_covers_final_api_update": first_crossing.updated_dt <= data_cutoff_dt,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    config_path = args.config.resolve()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    config = load_json(config_path)
    if config.get("schema_version") != 6:
        raise SystemExit("unsupported reconstruction config schema")

    source_checks: dict[str, Any] = {}
    source_paths: dict[str, Path] = {}
    for name in ("official_submissions", "api_checkpoint", "chronology"):
        source = config["sources"][name]
        path = resolve_path(config_path, source["path"])
        actual_hash = sha256(path)
        if actual_hash != source["sha256"]:
            raise SystemExit(f"{name} SHA-256 mismatch: expected {source['sha256']}, got {actual_hash}")
        source_paths[name] = path
        source_checks[name] = {"path": str(path.relative_to(ROOT)), "sha256": actual_hash, "hash_matches": True}

    raw_payload = load_json(source_paths["official_submissions"])
    if len(raw_payload.get("submissions", [])) != config["sources"]["official_submissions"]["expected_rows"]:
        raise SystemExit("official submission row count does not match the pinned manifest")
    checkpoint_payload = load_json(source_paths["api_checkpoint"])
    if len(checkpoint_payload) != config["sources"]["api_checkpoint"]["expected_rows"]:
        raise SystemExit("API checkpoint row count does not match the pinned manifest")
    checkpoint_comparison = compare_api_checkpoint(
        checkpoint_payload,
        raw_payload["submissions"],
    )
    if checkpoint_comparison["missing_ids"]:
        raise SystemExit("a row from the tracked API checkpoint is absent from the pinned response")
    submissions = normalize_submissions(raw_payload)
    by_id = {row.short_id: row for row in submissions}
    data_cutoff_dt = parse_iso(config["data_cutoff_at"])
    data_cutoff = verify_data_cutoff(config, submissions, data_cutoff_dt)
    frozen = [row for row in submissions if row.created_dt <= data_cutoff_dt]
    raw_frozen = [
        row
        for row in raw_payload["submissions"]
        if parse_iso(row["createdAt"]) <= data_cutoff_dt
    ]
    post_cut_updates = [
        row
        for row in raw_frozen
        if row.get("updatedAt") and parse_iso(row["updatedAt"]) > data_cutoff_dt
    ]
    if post_cut_updates:
        ids = ", ".join(row["id"][:7] for row in post_cut_updates[:10])
        raise SystemExit(
            "pre-cutoff rows were updated after the data cutoff; a later API fetch cannot "
            f"stand in for the historical row state ({ids})"
        )
    score_mismatches = [
        row
        for row in frozen
        if row.score != row.q * row.t
    ]
    if score_mismatches:
        ids = ", ".join(row.short_id for row in score_mismatches[:10])
        raise SystemExit(f"official score does not equal Q*T for metric-bearing rows: {ids}")

    reconciled, ledger_report = reconcile_ledger(source_paths["chronology"], submissions)
    if ledger_report["rows"] != config["sources"]["chronology"]["expected_rows"]:
        raise SystemExit("chronology row count does not match the pinned manifest")
    write_csv(output / "ledger_reconciliation.csv", reconciled)

    paper_ids = set(config["admission_policy"]["paper_admitted_curated_rejected_ids"])
    paper_rejected: list[Submission] = []
    note_evidence: dict[str, dict[str, Any]] = {}
    for short_id in sorted(paper_ids):
        row = by_id.get(short_id)
        if row is None or row.created_dt > data_cutoff_dt or row.status != "rejected":
            raise SystemExit(f"paper-admitted row is missing or invalid at the data cutoff: {short_id}")
        passes, excerpt = note_validation_evidence(row.note)
        note_evidence[short_id] = {"passes": passes, "excerpt": excerpt}
        if not passes:
            raise SystemExit(f"paper-admitted row lacks explicit complete zero-failure note evidence: {short_id}")
        paper_rejected.append(row)

    promoted = [row for row in frozen if row.is_promoted]
    official_frontier = pareto(frozen)
    expected_official = config["admission_policy"].get(
        "pinned_response_api_metric_pareto_ids_q_ascending",
        [],
    )
    actual_official = [row.short_id for row in official_frontier]

    paper_frontier = pareto([*promoted, *paper_rejected])
    expected_paper = config["admission_policy"].get(
        "paper_admitted_pareto_ids_q_ascending",
        [],
    )
    actual_paper = [row.short_id for row in paper_frontier]

    note_rejected = []
    note_rule_evidence: dict[str, dict[str, Any]] = {}
    for row in frozen:
        if row.status != "rejected":
            continue
        passes, excerpt = note_validation_evidence(row.note)
        if passes:
            note_rejected.append(row)
            note_rule_evidence[row.short_id] = {"passes": True, "excerpt": excerpt}
    note_frontier = pareto([*promoted, *note_rejected])
    note_ids = [row.short_id for row in note_frontier]
    expected_note = config["admission_policy"].get(
        "note_sensitivity_pareto_ids_q_ascending",
        [],
    )

    transition = attach_tracks(submissions, config)
    transition_output = []
    ledger_by_id = {row["official_submission"]: row for row in reconciled if row["official_submission"]}
    for selected, row in zip(config["transition_slice"], transition, strict=True):
        if row.created_dt > data_cutoff_dt:
            raise SystemExit(f"transition row falls after data cutoff: {row.short_id}")
        ledger = ledger_by_id.get(row.short_id)
        transition_output.append(
            {
                **row_dict(row),
                "track": selected["track"],
                "selection_basis": selected["selection_basis"],
                "chronology_publication_bucket": ledger["publication_bucket"] if ledger else "not_in_chronology",
                "chronology_source_state": ledger["source_state"] if ledger else "not_in_chronology",
            }
        )
    write_csv(output / "transition_slice.csv", transition_output)

    official_output = [row_dict(row) for row in official_frontier]
    write_csv(output / "pareto_pinned_api_metrics.csv", official_output)

    paper_output = []
    for row in paper_frontier:
        evidence = note_evidence.get(row.short_id)
        paper_output.append(row_dict(row, note_evidence=True if row.is_promoted else evidence["passes"], excerpt="official promotion" if row.is_promoted else evidence["excerpt"]))
    write_csv(output / "pareto_manifest.csv", paper_output)

    note_output = []
    for row in note_frontier:
        evidence = note_rule_evidence.get(row.short_id)
        note_output.append(row_dict(row, note_evidence=True, excerpt="official promotion" if row.is_promoted else evidence["excerpt"]))
    write_csv(output / "admitted_pareto_note_sensitivity.csv", note_output)

    current_promoted = [row for row in submissions if row.is_promoted]
    live_tip = min(current_promoted, key=lambda row: (row.score, row.created_dt, row.short_id))
    frozen_endpoint_id = config["data_cutoff"]["submission_id"]
    frozen_tip = by_id[frozen_endpoint_id]
    live_reconciliation = {
        "frozen_endpoint": row_dict(frozen_tip),
        "live_endpoint_at_fetch": row_dict(live_tip),
        "same_q": frozen_tip.q == live_tip.q,
        "toffoli_reduction": frozen_tip.t - live_tip.t,
        "toffoli_reduction_percent": round(100 * (frozen_tip.t - live_tip.t) / frozen_tip.t, 4),
        "score_reduction": frozen_tip.score - live_tip.score,
        "score_reduction_percent": round(100 * (frozen_tip.score - live_tip.score) / frozen_tip.score, 4),
        "live_is_context_only": True,
    }

    official_source = config["sources"]["official_submissions"]
    fetched_date = official_source["fetched_at"][:10]
    cut_date = config["data_cutoff_at"][:10]
    verification = {
        "schema_version": config["schema_version"],
        "reconstructed_from_snapshot_fetched_at": official_source["fetched_at"],
        "data_cutoff_at": config["data_cutoff_at"],
        "data_cutoff": data_cutoff,
        "source_checks": source_checks,
        "api_response": {
            "raw_rows": len(raw_payload["submissions"]),
            "metric_rows": len(submissions),
            "raw_rows_at_data_cutoff": len(raw_frozen),
            "metric_rows_at_data_cutoff": len(frozen),
            "pre_cut_rows_updated_after_cut": len(post_cut_updates),
            "retained_pre_cut_rows_unchanged_by_updated_at": not post_cut_updates,
            "retrospective_completeness_proven": False,
            "declared_population_complete_by_definition": True,
            "historical_database_exhaustiveness_claimed": False,
            "population_definition": config["publication_policy"]["population_definition"],
            "all_metric_scores_equal_q_times_t": not score_mismatches,
            "byte_identical_readback_at": official_source.get("byte_identical_readback_at"),
            "byte_identical_readback_query": official_source.get("byte_identical_readback_query"),
            "retrospective_limitations": [
                f"The {fetched_date} response cannot rule out a row created by {cut_date} and deleted before the fetch.",
                "The response has no pagination or completeness metadata.",
                f"A contemporaneous {cut_date} export or a maintainer append-only contract is required for an exhaustive historical claim.",
            ],
        },
        "api_checkpoint_comparison": checkpoint_comparison,
        "publication_policy": config["publication_policy"],
        "chronology_reconciliation": ledger_report,
        "transition_slice": {
            "count": len(transition),
            "ids": [row.short_id for row in transition],
            "within_selected_display_range": 10 <= len(transition) <= 15,
        },
        "pinned_response_api_metrics_pareto": {
            "expected_ids": expected_official,
            "actual_ids": actual_official,
            "matches_pinned_expectation": not expected_official or expected_official == actual_official,
        },
        "note_rule_sensitivity": {
            "mechanically_note_admitted_rejected_rows": len(note_rejected),
            "pareto_ids": note_ids,
            "expected_ids": expected_note,
            "matches_pinned_expectation": not expected_note or expected_note == note_ids,
            "official_only_ids": [short_id for short_id in actual_official if short_id not in set(note_ids)],
            "note_only_ids_after_refrontiering": [short_id for short_id in note_ids if short_id not in set(actual_official)],
        },
        "paper_admitted_pareto": {
            "expected_ids": expected_paper,
            "actual_ids": actual_paper,
            "matches_configured_expectation": not expected_paper or expected_paper == actual_paper,
            "official_only_ids": [short_id for short_id in actual_official if short_id not in set(actual_paper)],
            "paper_only_ids_after_refrontiering": [short_id for short_id in actual_paper if short_id not in set(actual_official)],
            "differs_from_api_metric_rule": actual_paper != actual_official,
        },
        "live_reconciliation": live_reconciliation,
    }
    write_json(output / "verification_report.json", verification)
    write_json(
        output / "figure_data.json",
        {
            "data_cutoff_at": config["data_cutoff_at"],
            "transition_slice": transition_output,
            "pinned_response_api_metrics_pareto": official_output,
            "note_rule_sensitivity_pareto": note_output,
            "paper_admitted_pareto": paper_output,
            "live_reconciliation": live_reconciliation,
        },
    )

    figure_config = config.get("figure", {})
    primary_set_name = figure_config.get("paper_primary_set", "api_metric")
    primary_sets = {
        "api_metric": official_frontier,
        "note_rule": note_frontier,
        "paper_admitted": paper_frontier,
    }
    if primary_set_name not in primary_sets:
        raise SystemExit(f"unsupported paper figure primary set: {primary_set_name}")
    paper_scene = build_paper_scene(transition, primary_sets[primary_set_name], figure_config)
    sensitivity_scene = build_sensitivity_scene(
        official_frontier,
        note_frontier,
        paper_frontier,
        figure_config,
    )
    for stem, scene in (("frontier_figure_paper", paper_scene), ("frontier_figure_policy_sensitivity", sensitivity_scene)):
        render_svg(scene, output / f"{stem}.svg")
        if not render_pdf(scene, output / f"{stem}.pdf"):
            raise SystemExit("reportlab is required to render the publication PDF")
        if not render_png(scene, output / f"{stem}.png"):
            raise SystemExit("Pillow is required to render the review PNG")

    generated_names = [
        "pareto_manifest.csv",
        "admitted_pareto_note_sensitivity.csv",
        "figure_data.json",
        "frontier_figure_paper.pdf",
        "frontier_figure_paper.png",
        "frontier_figure_paper.svg",
        "frontier_figure_policy_sensitivity.pdf",
        "frontier_figure_policy_sensitivity.png",
        "frontier_figure_policy_sensitivity.svg",
        "ledger_reconciliation.csv",
        "pareto_pinned_api_metrics.csv",
        "transition_slice.csv",
        "verification_report.json",
    ]
    generated_files = [output / name for name in generated_names]
    missing_generated = [path.name for path in generated_files if not path.is_file()]
    if missing_generated:
        raise SystemExit("missing generated outputs: " + ", ".join(missing_generated))
    implementation_files = [
        (ROOT / "README.md").resolve(),
        config_path,
        (ROOT / "requirements.txt").resolve(),
        *sorted((ROOT / "scripts").glob("*.py")),
        *sorted((ROOT / "tests").glob("*.py")),
    ]
    write_json(
        output / "source_manifest.json",
        {
            "schema_version": config["schema_version"],
            "data_cutoff_at": config["data_cutoff_at"],
            "sources": config["sources"],
            "implementation": {
                str(path.relative_to(ROOT)): {"sha256": sha256(path), "bytes": path.stat().st_size}
                for path in implementation_files
            },
            "outputs": {path.name: {"sha256": sha256(path), "bytes": path.stat().st_size} for path in generated_files},
        },
    )
    print(
        json.dumps(
            {
                "transition_points": len(transition),
                "pinned_response_api_metric_pareto_points": len(official_frontier),
                "note_rule_pareto_points": len(note_frontier),
                "paper_admitted_pareto_points": len(paper_frontier),
                "data_cutoff_submission": data_cutoff["submission_id"] if data_cutoff else None,
                "live_tip": live_tip.short_id,
                "output": str(output),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
