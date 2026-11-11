"""Data integrity tests for dates in Riksdag protocols.

The session checks use `test/data/riksdag-year.csv`.
"""

from datetime import datetime
from pathlib import Path
import re
import unittest

import polars as pl
from pyriksdagen.io import parse_tei
from pyriksdagen.utils import corpus_iterator, get_doc_dates, infer_metadata
from tqdm import tqdm
from trainerlog import get_logger


LOGGER = get_logger(name="docdate-integrity")
RIKSDAG_YEAR_PATH = Path("test/data/riksdag-year.csv")
MAX_SPAN_DAYS = 7

MAX_LONG_SPANS = 357
MAX_RANGE_OVERLAPS = 254
MAX_OUTSIDE_RIKSDAG_YEAR_RANGE = 285

CHAMBER_CODES = {
    "Första kammaren": "fk",
    "Andra kammaren": "ak",
    "Enkammarriksdagen": "ek",
}


def load_session_ranges():
    """Load session start and end dates from the CSV and group them by parliamentary year and chamber."""
    ranges = {}
    sessions = pl.read_csv(RIKSDAG_YEAR_PATH, try_parse_dates=True)
    for year, chamber, start, end in sessions.select(
        "parliament_year", "chamber", "start", "end"
    ).iter_rows():
        if start is not None and end is not None:
            ranges.setdefault((str(year), chamber), []).append((start, end))
    return ranges


def expected_ranges(protocol, session_ranges):
    """Return session ranges for the protocol's year folder.

    Include rows for its chamber and rows without a chamber.
    """
    folder = Path(protocol["path"]).parts[1]
    chamber = CHAMBER_CODES.get(protocol["chamber"])
    neutral_ranges = session_ranges.get((folder, None), ())
    if chamber is None:
        return neutral_ranges
    return (*session_ranges.get((folder, chamber), ()), *neutral_ranges)


def outside_session_dates(dates, ranges):
    """Return dates outside every session range, treating both endpoints as inclusive."""
    return [value for value in dates if not any(start <= value <= end for start, end in ranges)]


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
            cls.protocol_dates.append({
                "path": path,
                "chamber": metadata.get("chamber"),
                "year": metadata.get("year"),
                "raw": tuple(raw_dates),
                "parsed": tuple(sorted(parsed)),
            })

    def test_protocols_have_parseable_docdates(self):
        """Guarantee: every protocol has docDates and each value is a calendar date."""
        failures = 0
        for protocol in self.protocol_dates:
            if not protocol["raw"]:
                LOGGER.error("%s: missing docDate", protocol["path"])
                failures += 1
            elif len(protocol["raw"]) != len(protocol["parsed"]):
                failures += 1
        self.assertEqual(
            failures, 0, f"{failures} protocol(s) have missing or invalid docDates; see log."
        )

    def test_protocol_date_spans_are_not_longer_than_one_week(self):
        """Guarantee: the number of protocols whose earliest and latest docDates
        are more than seven days apart is within the limit.
        """
        failures = 0
        for protocol in self.protocol_dates:
            dates = protocol["parsed"]
            if dates:
                first, last = dates[0], dates[-1]
                if (last - first).days > MAX_SPAN_DAYS:
                    LOGGER.warning("%s: docDate span %s to %s", protocol["path"], first, last)
                    failures += 1
        self.assertLessEqual(
            failures, MAX_LONG_SPANS,
            f"{failures} protocols span more than a week (limit {MAX_LONG_SPANS}); see log.",
        )

    def test_protocol_date_ranges_do_not_overlap_in_sequence(self):
        """Guarantee: among adjacent dated protocols in path order, the number
        of pairs from the same chamber where the first protocol ends after the
        second begins is within the limit.
        """
        failures = 0
        previous = None
        for protocol in self.protocol_dates:
            if not protocol["parsed"]:
                continue
            if (
                previous is not None
                and previous["chamber"] == protocol["chamber"]
                and previous["parsed"][-1] > protocol["parsed"][0]
            ):
                LOGGER.warning(
                    "%s ends %s, after %s starts %s",
                    previous["path"], previous["parsed"][-1], protocol["path"], protocol["parsed"][0],
                )
                failures += 1
            previous = protocol
        self.assertLessEqual(
            failures, MAX_RANGE_OVERLAPS,
            f"{failures} adjacent date ranges move backward (limit {MAX_RANGE_OVERLAPS}); see log.",
        )

    def test_pre_1875_filename_dates_match_docdates(self):
        """Guarantee: if a protocol from before 1875 has a date in its filename,
        all its docDates match that date.
        """
        failures = 0
        for protocol in self.protocol_dates:
            year = protocol["year"]
            if not protocol["parsed"] or not year or year >= 1875:
                continue
            date_code = re.search(r"--(\d{4})$", Path(protocol["path"]).stem)
            if date_code is None:
                continue
            mmdd = date_code.group(1)
            expected = f"{year}-{mmdd[:2]}-{mmdd[2:]}"
            if set(protocol["raw"]) != {expected}:
                LOGGER.error("%s: expected %s, found %r", protocol["path"], expected, protocol["raw"])
                failures += 1
        self.assertEqual(
            failures, 0,
            f"{failures} pre-1875 protocols disagree with their filename date; see log.",
        )

    def test_protocols_have_expected_riksdag_year_ranges(self):
        """Guarantee: each dated protocol has a reference session range for its folder and chamber."""
        session_ranges = load_session_ranges()
        failures = 0
        for protocol in self.protocol_dates:
            if protocol["parsed"] and not expected_ranges(protocol, session_ranges):
                LOGGER.error("%s: no session range for %s", protocol["path"], protocol["chamber"])
                failures += 1
        self.assertEqual(
            failures, 0,
            f"{failures} protocols lack a reference session range; see log.",
        )

    def test_docdates_stay_inside_expected_riksdag_year_range(self):
        """Guarantee: among protocols with session ranges, the number with a
        docDate outside all applicable ranges is within the limit.
        """
        session_ranges = load_session_ranges()
        failures = 0
        for protocol in self.protocol_dates:
            if not protocol["parsed"]:
                continue
            ranges = expected_ranges(protocol, session_ranges)
            if ranges:
                outside = outside_session_dates(protocol["parsed"], ranges)
                if outside:
                    LOGGER.warning("%s: dates %s outside session ranges %s", protocol["path"], outside, ranges)
                    failures += 1
        self.assertLessEqual(
            failures, MAX_OUTSIDE_RIKSDAG_YEAR_RANGE,
            f"{failures} protocols outside session ranges (limit {MAX_OUTSIDE_RIKSDAG_YEAR_RANGE}); see log.",
        )

    def test_known_199192_out_of_range_docdates_are_detected(self):
        """Guarantee: the session check still detects unresolved out-of-range cases from issue #234."""
        session_ranges = load_session_ranges()
        known_dates = {
            "data/199192/prot-199192--003.xml": "1992-10-07",
            "data/199192/prot-199192--004.xml": "1992-10-08",
            "data/199192/prot-199192--131.xml": "1991-01-01",
        }
        for protocol in self.protocol_dates:
            path = protocol["path"]
            if path in known_dates and known_dates[path] in protocol["raw"]:
                ranges = expected_ranges(protocol, session_ranges)
                self.assertTrue(
                    ranges and outside_session_dates(protocol["parsed"], ranges),
                    f"{path}: known out-of-range docDate was not detected",
                )


if __name__ == "__main__":
    unittest.main()
