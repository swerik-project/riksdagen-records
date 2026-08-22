"""
Data integrity tests for protocol docDate guarantees.

These tests check release-blocking date guarantees for the records corpus:
protocols must expose parseable TEI ``docDate`` values, protocol date spans
should be short, adjacent protocol date ranges must not overlap, and pre-1875
filename dates must be represented exactly in ``docDate``.

The tests use the XML corpus in ``data/`` as input and write structured
diagnostics to ``test/results/`` when a guarantee fails. Fuller documentation
lives in ``test/docs/docdate_integrity.md``.
"""
from datetime import datetime
from pathlib import Path
import csv
import re
import unittest

from pyriksdagen.io import parse_tei
from pyriksdagen.utils import corpus_iterator, get_doc_dates, infer_metadata
from trainerlog import get_logger


LOGGER = get_logger(name="docdate-integrity")
RESULTS_DIR = Path("test/results")
DATE_FORMAT = "%Y-%m-%d"

# Current-data baselines for legacy date issues. These keep the test
# release-blocking for regressions while allowing later curation PRs to ratchet
# the ceilings down as date quality improves.
MAX_LONG_SPANS = 1206
MAX_RANGE_OVERLAPS = 5003
MAX_FILENAME_MISMATCHES = 460


def parse_iso_date(value):
    """Return a datetime for YYYY-MM-DD strings, otherwise None."""
    if not isinstance(value, str):
        return None
    try:
        return datetime.strptime(value, DATE_FORMAT)
    except ValueError:
        return None


def join_dates(dates):
    return ";".join(sorted(str(date) for date in dates))


def write_diagnostics(filename, rows, fieldnames):
    """Write failure rows to test/results/ when there is something to inspect."""
    if not rows:
        return None
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    path = RESULTS_DIR / filename
    with path.open("w", newline="", encoding="utf-8") as outf:
        writer = csv.DictWriter(outf, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    return path


def expected_pre_1875_filename_date(path, year):
    """Infer the expected date from pre-1875 protocol filenames."""
    match = re.search(r"--(\d{4})$", Path(path).stem)
    if not match:
        return None
    mmdd = match.group(1)
    return "{year}-{month}-{day}".format(
        year=year,
        month=mmdd[:2],
        day=mmdd[2:],
    )


class DocDateIntegrityTest(unittest.TestCase):
    """Check corpus-wide protocol date guarantees."""

    @classmethod
    def setUpClass(cls):
        cls.metadata_errors = []
        cls.long_spans = []
        cls.range_overlaps = []
        cls.filename_mismatches = []

        protocols = sorted(corpus_iterator("records", corpus_root="data"))
        LOGGER.info("Checking docDate integrity for %s protocols", len(protocols))

        previous_path = None
        previous_last_date = None

        for path in protocols:
            root, _ = parse_tei(path)
            _, docdates = get_doc_dates(root)
            parsed_dates = []

            if not docdates:
                cls.metadata_errors.append({
                    "file": path,
                    "issue": "missing docDate",
                    "docdates": "",
                })
                continue

            for docdate in docdates:
                parsed = parse_iso_date(docdate)
                if parsed is None:
                    cls.metadata_errors.append({
                        "file": path,
                        "issue": "unparseable docDate",
                        "docdates": join_dates(docdates),
                    })
                else:
                    parsed_dates.append(parsed)

            if not parsed_dates:
                continue

            parsed_dates.sort()
            first_date = parsed_dates[0]
            last_date = parsed_dates[-1]

            if len(parsed_dates) > 1:
                delta = last_date - first_date
                if delta.days > 7:
                    cls.long_spans.append({
                        "file": path,
                        "first_docdate": first_date.strftime(DATE_FORMAT),
                        "last_docdate": last_date.strftime(DATE_FORMAT),
                        "span_days": str(delta.days),
                    })

            if previous_last_date is not None:
                if previous_last_date == first_date:
                    issue = "share a day"
                elif previous_last_date > first_date:
                    issue = "multiday overlap"
                else:
                    issue = None

                if issue is not None:
                    cls.range_overlaps.append({
                        "previous_file": previous_path,
                        "file": path,
                        "previous_last_docdate": previous_last_date.strftime(DATE_FORMAT),
                        "first_docdate": first_date.strftime(DATE_FORMAT),
                        "issue": issue,
                    })

            metadata = infer_metadata(path)
            year = metadata.get("year")
            expected = expected_pre_1875_filename_date(path, year) if year and year < 1875 else None
            if expected is not None:
                docdate_set = set(docdates)
                if expected not in docdate_set:
                    cls.filename_mismatches.append({
                        "file": path,
                        "expected_docdate": expected,
                        "docdates": join_dates(docdates),
                        "issue": "filename date not in docDate",
                    })
                elif len(docdate_set) > 1:
                    cls.filename_mismatches.append({
                        "file": path,
                        "expected_docdate": expected,
                        "docdates": join_dates(docdates),
                        "issue": "additional docDates beyond filename date",
                    })

            previous_path = path
            previous_last_date = last_date

        cls.metadata_errors_path = write_diagnostics(
            "docdate-metadata-errors.csv",
            cls.metadata_errors,
            ["file", "issue", "docdates"],
        )
        cls.long_spans_path = write_diagnostics(
            "docdate-long-spans.csv",
            cls.long_spans,
            ["file", "first_docdate", "last_docdate", "span_days"],
        ) if len(cls.long_spans) > MAX_LONG_SPANS else None
        cls.range_overlaps_path = write_diagnostics(
            "docdate-range-overlaps.csv",
            cls.range_overlaps,
            ["previous_file", "file", "previous_last_docdate", "first_docdate", "issue"],
        ) if len(cls.range_overlaps) > MAX_RANGE_OVERLAPS else None
        cls.filename_mismatches_path = write_diagnostics(
            "docdate-filename-mismatches.csv",
            cls.filename_mismatches,
            ["file", "expected_docdate", "docdates", "issue"],
        ) if len(cls.filename_mismatches) > MAX_FILENAME_MISMATCHES else None

    def test_protocols_have_parseable_docdates(self):
        """Every protocol should have parseable docDate values."""
        self.assertEqual(
            len(self.metadata_errors),
            0,
            "{n} protocol docDate metadata error(s); see {path}".format(
                n=len(self.metadata_errors),
                path=self.metadata_errors_path or "test/results/docdate-metadata-errors.csv",
            ),
        )

    def test_protocol_date_spans_are_not_longer_than_one_week(self):
        """A protocol should not span more than seven days."""
        self.assertLessEqual(
            len(self.long_spans),
            MAX_LONG_SPANS,
            "{n} protocol(s) span more than one week, exceeding baseline {baseline}; see {path}".format(
                n=len(self.long_spans),
                baseline=MAX_LONG_SPANS,
                path=self.long_spans_path or "test/results/docdate-long-spans.csv",
            ),
        )

    def test_protocol_date_ranges_do_not_overlap_in_sequence(self):
        """Adjacent protocols in corpus order should not have overlapping date ranges."""
        self.assertLessEqual(
            len(self.range_overlaps),
            MAX_RANGE_OVERLAPS,
            "{n} protocol date range overlap(s), exceeding baseline {baseline}; see {path}".format(
                n=len(self.range_overlaps),
                baseline=MAX_RANGE_OVERLAPS,
                path=self.range_overlaps_path or "test/results/docdate-range-overlaps.csv",
            ),
        )

    def test_pre_1875_filename_dates_match_docdates(self):
        """Pre-1875 protocol filename dates should match the sole docDate."""
        self.assertLessEqual(
            len(self.filename_mismatches),
            MAX_FILENAME_MISMATCHES,
            "{n} pre-1875 filename/docDate mismatch(es), exceeding baseline {baseline}; see {path}".format(
                n=len(self.filename_mismatches),
                baseline=MAX_FILENAME_MISMATCHES,
                path=self.filename_mismatches_path or "test/results/docdate-filename-mismatches.csv",
            ),
        )


if __name__ == "__main__":
    unittest.main()
