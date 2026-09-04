"""Data integrity tests for protocol ``docDate`` metadata.

These tests check corpus-wide date guarantees for protocol XML files under
``data/``. They use ``pyriksdagen`` for corpus iteration, TEI parsing, date
extraction, and protocol metadata inference. Current data still contains known
legacy date issues, so the affected regression guards use explicit baselines;
curation pull requests should ratchet those baselines down as issues are fixed.

The authoritative documentation for these guarantees lives in this file. The
older ``test/docs/docdate_integrity.md`` file is legacy documentation.
"""

from collections import defaultdict
import unittest

from pyriksdagen.io import parse_tei
from pyriksdagen.utils import corpus_iterator, get_doc_dates, infer_metadata, parse_date
from tqdm import tqdm
from trainerlog import get_logger


MAX_LONG_SPAN_PROTOCOLS = 1206
MAX_SAME_CHAMBER_BACKWARDS_RANGES = 2753
MAX_PRE_1875_FILENAME_DOCDATE_MISMATCHES = 460
LOG_EXAMPLE_LIMIT = 20

LOGGER = get_logger(name="docdate-integrity")


def _read_protocol_docdates():
    """Parse protocol TEI once and cache the docDates used by the tests."""
    protocols = sorted(corpus_iterator("records", corpus_root="data"))
    LOGGER.info(f"Reading docDate metadata from {len(protocols)} protocol files")

    rows = []
    for path in tqdm(protocols, desc="Reading protocol docDates"):
        root, _ = parse_tei(path)
        _, docdates = get_doc_dates(root)
        parsed_docdates = []
        for docdate in docdates:
            if not docdate:
                continue
            parsed = parse_date(docdate)
            if parsed is not None:
                parsed_docdates.append((parsed, docdate))
        parsed_docdates = tuple(sorted(parsed_docdates))
        metadata = infer_metadata(path)

        rows.append(
            {
                "path": path,
                "chamber": metadata.get("chamber"),
                "year": metadata.get("year"),
                "docdates": tuple(docdates),
                "parsed_docdates": parsed_docdates,
            }
        )
    return rows


def _log_failure_examples(summary, examples, log_error=False):
    """Log a failure summary plus a bounded sample of example records."""
    log = LOGGER.error if log_error else LOGGER.warning
    log(summary)
    for example in examples[:LOG_EXAMPLE_LIMIT]:
        log(example)
    if len(examples) > LOG_EXAMPLE_LIMIT:
        log(f"... {len(examples) - LOG_EXAMPLE_LIMIT} additional example(s) omitted")


class DocDateIntegrityTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.protocol_docdates = _read_protocol_docdates()

    def test_protocols_have_parseable_docdates(self):
        """Guarantee: every protocol has at least one parseable ``docDate``.

        Why this matters: protocols without parseable meeting dates cannot be
        placed reliably in chronological order or linked to time-bounded person
        metadata.

        Data: scans protocol XML files under ``data/`` and extracts ``docDate``
        values with ``pyriksdagen.utils.get_doc_dates``.
        """
        failures = [
            f"{row['path']}: docDate values={row['docdates']!r}"
            for row in self.protocol_docdates
            if not row["parsed_docdates"]
        ]

        if failures:
            _log_failure_examples(
                f"{len(failures)} protocol(s) have no parseable docDate values",
                failures,
                log_error=True,
            )
        LOGGER.info(
            f"Protocols without parseable docDate values: {len(failures)} "
            f"of {len(self.protocol_docdates)}"
        )

        self.assertEqual(
            len(failures),
            0,
            f"{len(failures)} protocol(s) have no parseable docDate values; "
            "details were logged with trainerlog.",
        )

    def test_protocol_docdate_spans_do_not_exceed_current_baseline(self):
        """Guarantee: protocol ``docDate`` spans should not regress.

        Why this matters: a single protocol that spans more than seven days is
        usually a sign that OCR, segmentation, or date extraction has pulled in
        dates from surrounding source material.

        Data: scans protocol XML under ``data/``. The counted unit is a
        protocol whose first and last parseable ``docDate`` values are more
        than seven days apart.
        """
        failures = []
        for row in self.protocol_docdates:
            if not row["parsed_docdates"]:
                continue
            first_date, first_docdate = row["parsed_docdates"][0]
            last_date, last_docdate = row["parsed_docdates"][-1]
            if (last_date - first_date).days > 7:
                failures.append(f"{row['path']}: {first_docdate} to {last_docdate}")

        if failures:
            _log_failure_examples(
                f"{len(failures)} protocol(s) span more than one week; "
                f"accepted baseline is {MAX_LONG_SPAN_PROTOCOLS}",
                failures,
                log_error=len(failures) > MAX_LONG_SPAN_PROTOCOLS,
            )
        LOGGER.info(
            f"Protocols spanning more than one week: {len(failures)}; "
            f"accepted baseline: {MAX_LONG_SPAN_PROTOCOLS}"
        )

        self.assertLessEqual(
            len(failures),
            MAX_LONG_SPAN_PROTOCOLS,
            f"{len(failures)} protocol(s) span more than one week, exceeding "
            f"the accepted baseline of {MAX_LONG_SPAN_PROTOCOLS}; details were "
            "logged with trainerlog.",
        )

    def test_same_chamber_docdate_order_does_not_exceed_current_baseline(self):
        """Guarantee: same-chamber protocol date ranges should not move backward.

        Why this matters: chronological regressions within a chamber can break
        analyses that treat the corpus order as a meeting sequence. Separate
        chambers are parallel streams, and same-day adjacency is allowed.

        Data: scans protocol XML under ``data/``. The counted unit is an
        adjacent same-chamber protocol pair where the previous protocol's last
        parseable ``docDate`` is later than the next protocol's first parseable
        ``docDate``.
        """
        rows_by_chamber = defaultdict(list)
        for row in self.protocol_docdates:
            if row["parsed_docdates"]:
                rows_by_chamber[row["chamber"]].append(row)

        failures = []
        for chamber, rows in rows_by_chamber.items():
            previous = None
            for row in rows:
                first_date, first_docdate = row["parsed_docdates"][0]
                if previous:
                    previous_last_date, previous_last_docdate = previous[
                        "parsed_docdates"
                    ][-1]
                    if previous_last_date > first_date:
                        failures.append(
                            f"{chamber}: {previous['path']} ({previous_last_docdate}) "
                            f"before {row['path']} ({first_docdate})"
                        )
                previous = row

        if failures:
            _log_failure_examples(
                f"{len(failures)} same-chamber protocol date range(s) move "
                "backward; accepted baseline is "
                f"{MAX_SAME_CHAMBER_BACKWARDS_RANGES}",
                failures,
                log_error=len(failures) > MAX_SAME_CHAMBER_BACKWARDS_RANGES,
            )
        LOGGER.info(
            f"Same-chamber backward date ranges: {len(failures)}; "
            f"accepted baseline: {MAX_SAME_CHAMBER_BACKWARDS_RANGES}"
        )

        self.assertLessEqual(
            len(failures),
            MAX_SAME_CHAMBER_BACKWARDS_RANGES,
            f"{len(failures)} same-chamber protocol date range(s) move backward, "
            f"exceeding the accepted baseline of "
            f"{MAX_SAME_CHAMBER_BACKWARDS_RANGES}; details were logged with "
            "trainerlog.",
        )

    def test_pre_1875_filename_date_matches_sole_docdate_baseline(self):
        """Guarantee: pre-1875 filename dates should match the sole ``docDate``.

        Why this matters: early protocol filenames encode the meeting date, and
        extra or conflicting ``docDate`` values make those records ambiguous for
        chronological indexing and downstream date filters.

        Data: scans protocol XML under ``data/`` before 1875. The counted unit
        is a protocol where the filename date is not exactly the set of
        parseable ``docDate`` values.
        """
        failures = []
        for row in self.protocol_docdates:
            if row["year"] is None or row["year"] >= 1875:
                continue
            date_code = row["path"].rsplit(".", 1)[0].rsplit("-", 1)[-1]
            if len(date_code) != 4 or not date_code.isdigit():
                failures.append(f"{row['path']}: filename date code is {date_code!r}")
                continue

            expected = f"{row['year']}-{date_code[:2]}-{date_code[2:]}"
            observed = {docdate for _, docdate in row["parsed_docdates"]}
            if observed != {expected}:
                failures.append(
                    f"{row['path']}: expected only {expected}, observed "
                    f"{sorted(observed)}"
                )

        if failures:
            _log_failure_examples(
                f"{len(failures)} pre-1875 protocol filename date(s) mismatch "
                "docDate values; accepted baseline is "
                f"{MAX_PRE_1875_FILENAME_DOCDATE_MISMATCHES}",
                failures,
                log_error=len(failures)
                > MAX_PRE_1875_FILENAME_DOCDATE_MISMATCHES,
            )
        LOGGER.info(
            f"Pre-1875 filename/docDate mismatches: {len(failures)}; "
            f"accepted baseline: {MAX_PRE_1875_FILENAME_DOCDATE_MISMATCHES}"
        )

        self.assertLessEqual(
            len(failures),
            MAX_PRE_1875_FILENAME_DOCDATE_MISMATCHES,
            f"{len(failures)} pre-1875 protocol filename date(s) mismatch "
            "docDate values, exceeding the accepted baseline of "
            f"{MAX_PRE_1875_FILENAME_DOCDATE_MISMATCHES}; details were logged "
            "with trainerlog.",
        )


if __name__ == "__main__":
    unittest.main()
