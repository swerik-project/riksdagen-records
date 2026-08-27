#!/usr/bin/env python3
"""Require yearly speaker-mapping coverage to stay above a threshold."""

from __future__ import annotations

import os
import sys
import unittest
from math import ceil
from glob import glob
from pathlib import Path

from tqdm import tqdm


REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from quality.speaker_mapping_coverage import coverage, protocol_speaker_mapping_counts  # noqa: E402


DEFAULT_MIN_COVERAGE = 0.90


def min_coverage() -> float:
    return float(os.environ.get("SPEAKER_COVERAGE_MIN", DEFAULT_MIN_COVERAGE))


def additional_known_needed(known: int, unknown: int, threshold: float) -> int:
    """Return how many unknown rows must become known to reach ``threshold``."""
    total = known + unknown
    if total == 0 or coverage(known, unknown) >= threshold:
        return 0
    return max(0, ceil(threshold * total - known))


class TestSpeakerMappingCoverageThreshold(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.records = sorted(glob("data/*/*.xml"))

    def test_each_year_meets_minimum_coverage(self):
        threshold = min_coverage()
        by_year: dict[int, dict[str, int]] = {}

        for record in tqdm(self.records):
            year, known, unknown = protocol_speaker_mapping_counts(record)
            counts = by_year.setdefault(year, {"known": 0, "unknown": 0})
            counts["known"] += known
            counts["unknown"] += unknown

        below_threshold = []
        for year in sorted(by_year):
            known = by_year[year]["known"]
            unknown = by_year[year]["unknown"]
            year_coverage = coverage(known, unknown)
            if year_coverage < threshold:
                below_threshold.append(
                    (
                        year,
                        year_coverage,
                        known,
                        unknown,
                        additional_known_needed(known, unknown, threshold),
                    )
                )

        if below_threshold:
            details = "\n".join(
                (
                    f"{year}: coverage={year_coverage:.4f}, known={known}, "
                    f"unknown={unknown}, needs +{needed} known mappings"
                )
                for year, year_coverage, known, unknown, needed in below_threshold
            )
            self.fail(f"Speaker mapping coverage below {threshold:.3f}:\n{details}")


if __name__ == "__main__":
    unittest.main()
