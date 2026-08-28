"""
Data integrity tests for protocol docDate guarantees.

These tests check release-blocking date guarantees for the records corpus:
protocols must expose parseable TEI ``docDate`` values, protocol date spans
should be short, same-chamber protocol date ranges must not move backwards in
time, and pre-1875 filename dates must be represented exactly in ``docDate``.

The tests use the XML corpus in ``data/`` as input and write one structured
diagnostics table to ``test/results/docdate-integrity.csv`` when issues are
found. 
"""
from datetime import datetime
from pathlib import Path
import re
import unittest

import polars as pl
from pyriksdagen.io import parse_tei
from pyriksdagen.utils import corpus_iterator, get_doc_dates, infer_metadata
from trainerlog import get_logger


LOGGER = get_logger(name="docdate-integrity")
RESULTS_PATH = Path("test/results/docdate-integrity.csv")
DATE_FORMAT = "%Y-%m-%d"

# The threshold is one week: protocol docDate ranges should stay short enough
# to represent one sitting or a tightly bounded adjacent group of sittings.
MAX_SPAN_DAYS = 7

# Current-data baselines for legacy date issues. These keep the test
# release-blocking for regressions while allowing later curation PRs to ratchet
# the ceilings down as date quality improves.
MAX_LONG_SPANS = 1206
MAX_RANGE_OVERLAPS = 2753
MAX_FILENAME_MISMATCHES = 460

DIAGNOSTIC_COLUMNS = [
    "file",
    "error_type",
    "issue",
    "docdates",
    "first_docdate",
    "last_docdate",
    "span_days",
    "previous_file",
    "previous_chamber",
    "chamber",
    "previous_last_docdate",
    "expected_docdate",
]

_DOC_DATE_ERRORS = None


def parse_iso_date(value):
    """Return a datetime for YYYY-MM-DD strings, otherwise None."""
    if not isinstance(value, str):
        return None
    try:
        return datetime.strptime(value, DATE_FORMAT)
    except ValueError:
        return None


def format_date(value):
    return value.strftime(DATE_FORMAT)


def join_dates(dates):
    return ";".join(sorted(str(date) for date in dates))


def empty_error_row():
    return {column: "" for column in DIAGNOSTIC_COLUMNS}


def docdate_error(error_type, file, issue, **fields):
    row = empty_error_row()
    row.update(
        {
            "file": str(file),
            "error_type": error_type,
            "issue": issue,
            **fields,
        }
    )
    return row


def expected_pre_1875_filename_date(path, year):
    """Infer the expected date from pre-1875 protocol filenames."""
    match = re.search(r"--(\d{4})$", Path(path).stem)
    if match is None:
        return None
    mmdd = match.group(1)
    return f"{year}-{mmdd[:2]}-{mmdd[2:]}"


def collect_docdate_errors():
    errors = []
    previous_path = None
    previous_chamber = None
    previous_last_date = None

    protocols = sorted(corpus_iterator("records", corpus_root="data"))
    LOGGER.info("Checking docDate integrity for %s protocols", len(protocols))

    for path in protocols:
        metadata = infer_metadata(path)
        chamber = metadata.get("chamber")
        root, _ = parse_tei(path)
        _, docdates = get_doc_dates(root)

        if not docdates:
            errors.append(
                docdate_error(
                    "missing_docdate",
                    path,
                    "missing docDate",
                    docdates="",
                )
            )
        else:
            parsed_dates = []
            for docdate in docdates:
                parsed = parse_iso_date(docdate)
                if parsed is None:
                    errors.append(
                        docdate_error(
                            "unparseable_docdate",
                            path,
                            "unparseable docDate",
                            docdates=join_dates(docdates),
                        )
                    )
                else:
                    parsed_dates.append(parsed)

            if parsed_dates:
                parsed_dates.sort()
                first_date = parsed_dates[0]
                last_date = parsed_dates[-1]
                first_docdate = format_date(first_date)
                last_docdate = format_date(last_date)

                if len(parsed_dates) > 1:
                    delta = last_date - first_date
                    if delta.days > MAX_SPAN_DAYS:
                        errors.append(
                            docdate_error(
                                "long_span",
                                path,
                                "protocol spans more than one week",
                                first_docdate=first_docdate,
                                last_docdate=last_docdate,
                                span_days=str(delta.days),
                            )
                        )

                if (
                    previous_last_date is not None
                    and previous_chamber == chamber
                    and previous_last_date > first_date
                ):
                    errors.append(
                        docdate_error(
                            "range_overlap",
                            path,
                            "same-chamber date range overlap",
                            previous_file=str(previous_path),
                            previous_chamber=str(previous_chamber),
                            chamber=str(chamber),
                            previous_last_docdate=format_date(previous_last_date),
                            first_docdate=first_docdate,
                        )
                    )

                year = metadata.get("year")
                expected = (
                    expected_pre_1875_filename_date(path, year)
                    if year and year < 1875
                    else None
                )
                if expected is not None:
                    docdate_set = set(docdates)
                    if expected not in docdate_set:
                        errors.append(
                            docdate_error(
                                "filename_mismatch",
                                path,
                                "filename date not in docDate",
                                expected_docdate=expected,
                                docdates=join_dates(docdates),
                            )
                        )
                    elif len(docdate_set) > 1:
                        errors.append(
                            docdate_error(
                                "filename_mismatch",
                                path,
                                "additional docDates beyond filename date",
                                expected_docdate=expected,
                                docdates=join_dates(docdates),
                            )
                        )

                previous_path = path
                previous_chamber = chamber
                previous_last_date = last_date

    return errors


def docdate_errors():
    global _DOC_DATE_ERRORS

    if _DOC_DATE_ERRORS is None:
        errors = collect_docdate_errors()
        _DOC_DATE_ERRORS = pl.DataFrame(errors, schema=DIAGNOSTIC_COLUMNS)
        if len(_DOC_DATE_ERRORS) > 0:
            RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
            _DOC_DATE_ERRORS = _DOC_DATE_ERRORS.sort(["file", "error_type"])
            _DOC_DATE_ERRORS.write_csv(RESULTS_PATH)

    return _DOC_DATE_ERRORS


def errors_of_type(error_type):
    return docdate_errors().filter(pl.col("error_type") == error_type)


def test_protocols_have_parseable_docdates():
    """Every protocol should have parseable docDate values."""
    df_missing = errors_of_type("missing_docdate")
    df_unparseable = errors_of_type("unparseable_docdate")
    metadata_errors = len(df_missing) + len(df_unparseable)
    assert metadata_errors == 0, (
        f"{metadata_errors} protocol docDate metadata error(s); "
        f"see {RESULTS_PATH}"
    )


def test_protocol_date_spans_are_not_longer_than_one_week():
    """A protocol should not span more than seven days."""
    df_long = errors_of_type("long_span")
    assert len(df_long) <= MAX_LONG_SPANS, (
        f"{len(df_long)} protocol(s) span more than one week, "
        f"exceeding baseline {MAX_LONG_SPANS}; see {RESULTS_PATH}"
    )


def test_protocol_date_ranges_do_not_overlap_in_sequence():
    """Adjacent same-chamber protocols should not move backwards in time."""
    df_overlap = errors_of_type("range_overlap")
    assert len(df_overlap) <= MAX_RANGE_OVERLAPS, (
        f"{len(df_overlap)} protocol date range overlap(s), "
        f"exceeding baseline {MAX_RANGE_OVERLAPS}; see {RESULTS_PATH}"
    )


def test_pre_1875_filename_dates_match_docdates():
    """Pre-1875 protocol filename dates should match the sole docDate."""
    df_filename = errors_of_type("filename_mismatch")
    assert len(df_filename) <= MAX_FILENAME_MISMATCHES, (
        f"{len(df_filename)} pre-1875 filename/docDate mismatch(es), "
        f"exceeding baseline {MAX_FILENAME_MISMATCHES}; see {RESULTS_PATH}"
    )


def load_tests(loader, tests, pattern):
    suite = unittest.TestSuite()
    suite.addTest(unittest.FunctionTestCase(test_protocols_have_parseable_docdates))
    suite.addTest(
        unittest.FunctionTestCase(test_protocol_date_spans_are_not_longer_than_one_week)
    )
    suite.addTest(
        unittest.FunctionTestCase(test_protocol_date_ranges_do_not_overlap_in_sequence)
    )
    suite.addTest(unittest.FunctionTestCase(test_pre_1875_filename_dates_match_docdates))
    return suite


if __name__ == "__main__":
    unittest.main()
