"""
Data integrity tests for protocol docDate guarantees.

These tests check release-blocking date guarantees for the records corpus:
protocols must expose parseable TEI ``docDate`` values, protocol date spans
should be short, same-chamber protocol date ranges must not move backwards in
time, pre-1875 filename dates must be represented exactly in ``docDate``, and
``docDate`` values should fall inside the expected Riksdag year for the folder.

The tests use the XML corpus in ``data/`` as input and write one structured
diagnostics table to ``test/results/docdate-integrity.csv`` when issues are
found. 
"""
from datetime import datetime
from pathlib import Path
import re
import unittest
import tqdm

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
MAX_OUTSIDE_RIKSDAG_YEAR_RANGE = 626
MAX_MISSING_RIKSDAG_YEAR_RANGE = 0

RIKSDAG_YEAR_PATH = Path("test/data/riksdag-year.csv")
CHAMBER_CODES = {
    "Första kammaren": "fk",
    "Andra kammaren": "ak",
    "Enkammarriksdagen": "ek",
}
KNOWN_199192_OUT_OF_RANGE_DOCDATES = {
    "data/199192/prot-199192--003.xml": {"1992-10-07"},
    "data/199192/prot-199192--004.xml": {"1992-10-08"},
    "data/199192/prot-199192--131.xml": {"1991-01-01"},
}

_DOC_DATE_ERRORS = None
_RIKSDAG_YEAR_RANGES = None


def parse_iso_date(value):
    """Return a datetime for YYYY-MM-DD strings, otherwise None."""
    try:
        return datetime.strptime(value, DATE_FORMAT).date()
    except:
        LOGGER.error(f"Could not parse date: {value}")
        return None

def join_ranges(ranges):
    return ";".join(
        f"{start.strftime(DATE_FORMAT)}..{end.strftime(DATE_FORMAT)}" for start, end in ranges
    )

def docdate_error(error_type, file, issue, **fields):
    return {
            "file": str(file),
            "error_type": error_type,
            "issue": issue,
            **fields,
        }

def expected_pre_1875_filename_date(path, year):
    """Infer the expected date from pre-1875 protocol filenames."""
    match = re.search(r"--(\d{4})$", Path(path).stem)
    if match is None:
        return None
    mmdd = match.group(1)
    return f"{year}-{mmdd[:2]}-{mmdd[2:]}"


def load_riksdag_year_ranges():
    """Load expected Riksdag-year ranges from the vendored test fixture."""
    global _RIKSDAG_YEAR_RANGES
    if _RIKSDAG_YEAR_RANGES is not None:
        return _RIKSDAG_YEAR_RANGES

    if not RIKSDAG_YEAR_PATH.exists():
        raise FileNotFoundError(
            f"Missing {RIKSDAG_YEAR_PATH}; refresh it from "
            "../riksdagen-persons/data/riksdag-year.csv"
        )

    ranges = {}
    LOGGER.info("Loading Riksdag year ranges from % s", RIKSDAG_YEAR_PATH)
    rd_df = pl.read_csv(RIKSDAG_YEAR_PATH, try_parse_dates=True)
    rd_df = rd_df.filter(pl.col("start").is_not_null() & pl.col("end").is_not_null())
    for row in rd_df.to_dicts():
        key = (str(row["parliament_year"]), row.get("chamber", None))
        ranges.setdefault(key, []).append((row["start"], row["end"]))

    _RIKSDAG_YEAR_RANGES = ranges
    return _RIKSDAG_YEAR_RANGES


def expected_riksdag_year_ranges(path, chamber):
    """Return date ranges that are valid for a protocol's folder and chamber."""
    folder = Path(path).parts[1]
    ranges = load_riksdag_year_ranges()
    chamber_code = CHAMBER_CODES.get(chamber)
    expected = []
    if chamber_code is not None:
        expected.extend(ranges.get((folder, chamber_code), []))
    expected.extend(ranges.get((folder, None), []))
    return sorted(expected)


def dates_outside_ranges(parsed_dates, expected_ranges):
    return [
        docdate
        for docdate, parsed in parsed_dates
        if not any(start <= parsed <= end for start, end in expected_ranges)
    ]


def collect_docdate_errors():
    errors = []
    previous_path = None
    previous_chamber = None
    previous_last_date = None

    protocols = sorted(corpus_iterator("records", corpus_root="data"))
    LOGGER.info("Checking docDate integrity for %s protocols", len(protocols))

    for path in tqdm.tqdm(protocols):
        metadata = infer_metadata(path)
        chamber = metadata.get("chamber")
        root, _ = parse_tei(path)
        _, docdates = get_doc_dates(root)

        if not docdates:
            errors.append(
                docdate_error(
                    "missing_docdate",
                    path,
                    "missing docDate"
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
                            docdates=list(docdates),
                        )
                    )
                else:
                    parsed_dates.append(parsed)

            if parsed_dates:
                parsed_dates.sort()
                first_date = parsed_dates[0]
                last_date = parsed_dates[-1]

                if len(parsed_dates) > 1:
                    delta = last_date - first_date
                    if delta.days > MAX_SPAN_DAYS:
                        errors.append(
                            docdate_error(
                                "long_span",
                                path,
                                "protocol spans more than one week",
                                first_docdate=first_date,
                                last_docdate=last_date,
                                span_days=delta.days,
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
                            previous_chamber=previous_chamber,
                            chamber=chamber,
                            previous_last_docdate=previous_last_date,
                            first_docdate=first_date,
                        )
                    )

                expected_ranges = expected_riksdag_year_ranges(path, chamber)
                if not expected_ranges:
                    errors.append(
                        docdate_error(
                            "missing_riksdag_year_range",
                            path,
                            "missing expected Riksdag-year range for folder/chamber",
                            chamber=chamber,
                        )
                    )
                else:
                    outside_docdates = dates_outside_ranges(
                        [(date.strftime(DATE_FORMAT), date) for date in parsed_dates],
                        expected_ranges,
                    )
                    if outside_docdates:
                        if len(outside_docdates) == len(parsed_dates):
                            issue = "all docDates outside expected Riksdag year range"
                        else:
                            issue = "some docDates outside expected Riksdag year range"
                        errors.append(
                            docdate_error(
                                "outside_riksdag_year_range",
                                path,
                                issue,
                                docdates=list(docdates),
                                expected_start=expected_ranges[0][0],
                                expected_end=expected_ranges[-1][1],
                                expected_ranges=join_ranges(expected_ranges),
                                outside_docdates=list(outside_docdates),
                            )
                        )

                year = metadata.get("year")
                expected = None
                if year and year < 1875:
                    expected = expected_pre_1875_filename_date(path, year)
                
                if expected is not None:
                    docdate_set = set(docdates)
                    if expected not in docdate_set:
                        errors.append(
                            docdate_error(
                                "filename_mismatch",
                                path,
                                "filename date not in docDate",
                                expected_docdate=expected,
                                docdates=list(docdates),
                            )
                        )
                    elif len(docdate_set) > 1:
                        errors.append(
                            docdate_error(
                                "filename_mismatch",
                                path,
                                "additional docDates beyond filename date",
                                expected_docdate=expected,
                                docdates=list(docdates),
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
        _DOC_DATE_ERRORS = pl.DataFrame(errors, infer_schema_length=10000)
        if len(_DOC_DATE_ERRORS) > 0:
            RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
            _DOC_DATE_ERRORS = _DOC_DATE_ERRORS.sort(["file", "error_type"])
            _DOC_DATE_ERRORS = _DOC_DATE_ERRORS.with_columns(pl.col("docdates").list.join("; "))
            _DOC_DATE_ERRORS = _DOC_DATE_ERRORS.with_columns(pl.col("outside_docdates").list.join("; "))
            _DOC_DATE_ERRORS.write_csv(RESULTS_PATH)

    return _DOC_DATE_ERRORS


class TestStringMethods(unittest.TestCase):
    def test_protocols_have_parseable_docdates(self):
        """Every protocol should have parseable docDate values."""
        df = docdate_errors()
        df_missing = df.filter(pl.col("error_type") == "missing_docdate")
        df_unparseable = df.filter(pl.col("error_type") == "unparseable_docdate")
        metadata_errors = len(df_missing) + len(df_unparseable)
        self.assertEqual(metadata_errors, 0, 
            f"{metadata_errors} protocol docDate metadata error(s); see {RESULTS_PATH}"
        )


    def test_protocol_date_spans_are_not_longer_than_one_week(self):
        """A protocol should not span more than seven days."""
        df_long = docdate_errors().filter(pl.col("error_type") == "long_span")
        self.assertLessEqual(len(df_long), MAX_LONG_SPANS, 
            f"{len(df_long)} protocol(s) span more than one week, exceeding baseline {MAX_LONG_SPANS}; see {RESULTS_PATH}"
        )


    def test_protocol_date_ranges_do_not_overlap_in_sequence(self):
        """Adjacent same-chamber protocols should not move backwards in time."""
        df_overlap =docdate_errors().filter(pl.col("error_type") == "range_overlap")
        self.assertLessEqual(len(df_overlap), MAX_RANGE_OVERLAPS, 
            f"{len(df_overlap)} protocol date range overlap(s), exceeding baseline {MAX_RANGE_OVERLAPS}; see {RESULTS_PATH}"
        )


    def test_pre_1875_filename_dates_match_docdates(self):
        """Pre-1875 protocol filename dates should match the sole docDate."""
        df_filename = docdate_errors().filter(pl.col("error_type") == "filename_mismatch")
        self.assertLessEqual(len(df_filename), MAX_FILENAME_MISMATCHES, 
            f"{len(df_filename)} pre-1875 filename/docDate mismatch(es), exceeding baseline {MAX_FILENAME_MISMATCHES}; see {RESULTS_PATH}"
        )


    def test_docdates_stay_inside_expected_riksdag_year_range(self):
        """Protocol docDates should stay inside the Riksdag year implied by the folder."""
        df_outside = docdate_errors().filter(pl.col("error_type") == "outside_riksdag_year_range")
        self.assertLessEqual(len(df_outside), MAX_OUTSIDE_RIKSDAG_YEAR_RANGE, (
            f"{len(df_outside)} protocol(s) have docDates outside the expected "
            f"Riksdag year range, exceeding baseline "
            f"{MAX_OUTSIDE_RIKSDAG_YEAR_RANGE}; see {RESULTS_PATH}"
        ))


    def test_protocols_have_expected_riksdag_year_ranges(self):
        """Every protocol folder/chamber should have an expected Riksdag-year range."""
        df_missing = docdate_errors().filter(pl.col("error_type") == "missing_riksdag_year_range")
        self.assertLessEqual(len(df_missing), MAX_MISSING_RIKSDAG_YEAR_RANGE, (
            f"{len(df_missing)} protocol(s) lack expected Riksdag-year ranges, "
            f"exceeding baseline {MAX_MISSING_RIKSDAG_YEAR_RANGE}; see {RESULTS_PATH}"
        ))


    def test_known_199192_out_of_range_docdates_are_reported(self):
        """Known issue-234 examples should be visible in range diagnostics until fixed."""
        df_outside = docdate_errors().filter(pl.col("error_type") == "outside_riksdag_year_range")
        rows = {
            row["file"]: set(str(row["outside_docdates"]).split(";"))
            for row in df_outside.select(["file", "outside_docdates"]).to_dicts()
        }
        missing = []
        for path, known_docdates in KNOWN_199192_OUT_OF_RANGE_DOCDATES.items():
            if Path(path).exists():
                root, _ = parse_tei(path)
                _, current_docdates = get_doc_dates(root)
                if known_docdates.intersection(current_docdates) and path not in rows:
                    missing.append(path)

        self.assertFalse(missing, 
            f"known issue-234 out-of-range docDate examples were not reported: {missing}; see {RESULTS_PATH}"
        )


if __name__ == "__main__":
    unittest.main()
