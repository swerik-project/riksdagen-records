#!/usr/bin/env python3
"""Shared speaker-mapping coverage utilities."""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Iterable

from pyriksdagen.io import parse_tei
from pyriksdagen.utils import infer_metadata


def protocol_speaker_mapping_counts(protocol_path: str | Path) -> tuple[int, int, int]:
    """Return ``(year, known, unknown)`` speaker-attribution counts for one protocol.

    This intentionally mirrors the metric used by
    ``qe_speaker-mapping-coverage.py``: every direct child of a protocol
    ``div`` with a ``who`` attribute is counted as either known or unknown.
    """
    protocol_path = str(protocol_path)
    root, ns = parse_tei(protocol_path, get_ns=True)
    metadata = infer_metadata(protocol_path)
    year = int(str(metadata.get("year"))[:4])

    known = 0
    unknown = 0
    for div in root.findall(f".//{ns['tei_ns']}div"):
        for elem in div:
            who = elem.attrib.get("who")
            if who is None:
                continue
            if who == "unknown":
                unknown += 1
            else:
                known += 1

    return year, known, unknown


def coverage(known: int, unknown: int) -> float:
    """Return known-speaker coverage for a count pair."""
    total = known + unknown
    return known / total if total else 1.0


def aggregate_yearly_counts(records: Iterable[str | Path]) -> list[dict[str, int | float]]:
    """Aggregate speaker-mapping counts by year."""
    by_year: dict[int, dict[str, int]] = defaultdict(lambda: {"known": 0, "unknown": 0})

    for record in records:
        year, known, unknown = protocol_speaker_mapping_counts(record)
        by_year[year]["known"] += known
        by_year[year]["unknown"] += unknown

    rows = []
    for year in sorted(by_year):
        known = by_year[year]["known"]
        unknown = by_year[year]["unknown"]
        rows.append(
            {
                "year": year,
                "known": known,
                "unknown": unknown,
                "coverage": coverage(known, unknown),
            }
        )
    return rows
