"""Release checks for meeting dates in protocol TEI and the session fixture."""

from collections import defaultdict
from datetime import date, datetime
from pathlib import Path
import re
from typing import NamedTuple, Optional
import unittest

import polars as pl
from pyriksdagen.io import parse_tei
from pyriksdagen.utils import corpus_iterator, get_doc_dates, infer_metadata
from tqdm import tqdm
from trainerlog import get_logger


LOGGER = get_logger(name="docdate-integrity")
RIKSDAG_YEAR_PATH = Path("test/data/riksdag-year.csv")
MAX_SPAN_DAYS = 7

# Keep the release limits from dev. Later curation can ratchet them down.
MAX_LONG_SPANS = 515
MAX_RANGE_OVERLAPS = 733
MAX_FILENAME_MISMATCHES = 0
MAX_OUTSIDE_RIKSDAG_YEAR_RANGE = 411
MAX_MISSING_RIKSDAG_YEAR_RANGE = 0

CHAMBER_CODES = {
    "Första kammaren": "fk",
    "Andra kammaren": "ak",
    "Enkammarriksdagen": "ek",
}


class ProtocolDates(NamedTuple):
    path: str
    chamber: Optional[str]
    year: Optional[int]
    raw: tuple[Optional[str], ...]
    parsed: tuple[date, ...]


class DocDateIntegrityTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Share the parsed inputs so the suite reads each corpus XML file once.
        cls.protocol_dates = []
        paths = sorted(corpus_iterator("records", corpus_root="data"))
        LOGGER.info("Reading docDates from %s protocols", len(paths))
        for path in tqdm(paths, desc="Reading protocol docDates"):
            root, _ = parse_tei(path)
            _, raw_dates = get_doc_dates(root)
            parsed = []
            for value in raw_dates:
                try:
                    parsed.append(datetime.strptime(value, "%Y-%m-%d").date())
                except (TypeError, ValueError):
                    LOGGER.error("%s: unparseable docDate %r", path, value)
            metadata = infer_metadata(path)
            cls.protocol_dates.append(
                ProtocolDates(
                    path, metadata.get("chamber"), metadata.get("year"),
                    tuple(raw_dates), tuple(sorted(parsed)),
                )
            )

        cls.session_ranges = defaultdict(list)
        sessions = pl.read_csv(RIKSDAG_YEAR_PATH, try_parse_dates=True)
        for year, chamber, start, end in sessions.select(
            "parliament_year", "chamber", "start", "end"
        ).iter_rows():
            if start is not None and end is not None:
                cls.session_ranges[str(year), chamber].append((start, end))

    def test_protocols_have_parseable_docdates(self):
        """Guarantee: every protocol has docDates and each value is a calendar date."""
        failures = 0
        for protocol in self.protocol_dates:
            if not protocol.raw:
                LOGGER.error("%s: missing docDate", protocol.path)
                failures += 1
            failures += len(protocol.raw) - len(protocol.parsed)
        self.assertEqual(failures, 0, f"{failures} missing or invalid docDate values; see log.")

    def test_protocol_date_spans_are_not_longer_than_one_week(self):
        """Guarantee: the number of protocols spanning more than a week cannot increase past the limit."""
        failures = 0
        for protocol in self.protocol_dates:
            if protocol.parsed:
                first, last = protocol.parsed[0], protocol.parsed[-1]
                if (last - first).days > MAX_SPAN_DAYS:
                    LOGGER.warning("%s: docDate span %s to %s", protocol.path, first, last)
                    failures += 1
        self.assertLessEqual(
            failures, MAX_LONG_SPANS,
            f"{failures} protocols span more than a week (limit {MAX_LONG_SPANS}); see log.",
        )

    def test_protocol_date_ranges_do_not_overlap_in_sequence(self):
        """Guarantee: adjacent dated protocols in the same chamber stay in order within the limit."""
        failures = 0
        previous = None
        for protocol in self.protocol_dates:
            if not protocol.parsed:
                continue
            if (
                previous is not None
                and previous.chamber == protocol.chamber
                and previous.parsed[-1] > protocol.parsed[0]
            ):
                LOGGER.warning(
                    "%s ends %s, after %s starts %s",
                    previous.path, previous.parsed[-1], protocol.path, protocol.parsed[0],
                )
                failures += 1
            previous = protocol
        self.assertLessEqual(
            failures, MAX_RANGE_OVERLAPS,
            f"{failures} adjacent date ranges move backward (limit {MAX_RANGE_OVERLAPS}); see log.",
        )

    def test_pre_1875_filename_dates_match_docdates(self):
        """Guarantee: an encoded pre-1875 filename date is the only distinct docDate."""
        failures = 0
        for protocol in self.protocol_dates:
            if not protocol.parsed or not protocol.year or protocol.year >= 1875:
                continue
            date_code = re.search(r"--(\d{4})$", Path(protocol.path).stem)
            if date_code is None:
                continue
            mmdd = date_code.group(1)
            expected = f"{protocol.year}-{mmdd[:2]}-{mmdd[2:]}"
            if set(protocol.raw) != {expected}:
                LOGGER.error("%s: expected %s, found %r", protocol.path, expected, protocol.raw)
                failures += 1
        self.assertLessEqual(
            failures, MAX_FILENAME_MISMATCHES,
            f"{failures} pre-1875 protocols disagree with their filename date; see log.",
        )

    def _expected_ranges(self, protocol):
        """Return session intervals for this folder and chamber, including chamber-neutral rows."""
        folder = Path(protocol.path).parts[1]
        chamber = CHAMBER_CODES.get(protocol.chamber)
        if chamber is None:
            return self.session_ranges.get((folder, None), ())
        return (
            *self.session_ranges.get((folder, chamber), ()),
            *self.session_ranges.get((folder, None), ()),
        )

    @staticmethod
    def _outside_session_dates(protocol, ranges):
        return [
            value for value in protocol.parsed
            if not any(start <= value <= end for start, end in ranges)
        ]

    def test_protocols_have_expected_riksdag_year_ranges(self):
        """Guarantee: each dated protocol has a reference session range for its folder and chamber."""
        failures = 0
        for protocol in self.protocol_dates:
            if protocol.parsed and not self._expected_ranges(protocol):
                LOGGER.error("%s: no session range for %s", protocol.path, protocol.chamber)
                failures += 1
        self.assertLessEqual(
            failures, MAX_MISSING_RIKSDAG_YEAR_RANGE,
            f"{failures} protocols lack a reference session range; see log.",
        )

    def test_docdates_stay_inside_expected_riksdag_year_range(self):
        """Guarantee: protocols outside their reference session ranges stay within the release limit."""
        failures = 0
        for protocol in self.protocol_dates:
            if not protocol.parsed:
                continue
            ranges = self._expected_ranges(protocol)
            if ranges:
                outside = self._outside_session_dates(protocol, ranges)
                if outside:
                    LOGGER.warning("%s: dates %s outside session ranges %s", protocol.path, outside, ranges)
                    failures += 1
        self.assertLessEqual(
            failures, MAX_OUTSIDE_RIKSDAG_YEAR_RANGE,
            f"{failures} protocols outside session ranges (limit {MAX_OUTSIDE_RIKSDAG_YEAR_RANGE}); see log.",
        )

    def test_known_199192_out_of_range_docdates_are_detected(self):
        """Guarantee: the session check still detects unresolved out-of-range cases from issue #234."""
        known_dates = {
            "data/199192/prot-199192--003.xml": "1992-10-07",
            "data/199192/prot-199192--004.xml": "1992-10-08",
            "data/199192/prot-199192--131.xml": "1991-01-01",
        }
        for protocol in self.protocol_dates:
            if protocol.path in known_dates and known_dates[protocol.path] in protocol.raw:
                ranges = self._expected_ranges(protocol)
                self.assertTrue(
                    ranges and self._outside_session_dates(protocol, ranges),
                    f"{protocol.path}: known out-of-range docDate was not detected",
                )


if __name__ == "__main__":
    unittest.main()
