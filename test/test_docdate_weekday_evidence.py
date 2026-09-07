"""
Data integrity test for weekday/date evidence in protocol body notes.

The records corpus often stores printed sitting headings and running headers as
short TEI ``note`` elements in the protocol body.  This test extracts clear
Swedish weekday/date evidence of the form ``Tisdagen den 7 oktober`` or
``Tisdagen den 7 oktober 1986`` from parsed note text and checks that the named
weekday matches the calendar date.

The test is diagnostic-first.  An impossible weekday/date pair can mean that a
false header date was copied into ``docDate``, but it can also mean that the
body text itself contains an OCR error.  The test therefore reports both
metadata-supporting and text-only impossible evidence without applying any
correction.
"""
from datetime import date
import os
from pathlib import Path
import re
import unittest

import dateparser
import polars as pl
import tqdm

from pyriksdagen.io import parse_tei
from pyriksdagen.utils import corpus_iterator, get_doc_dates, infer_metadata
from trainerlog import get_logger


LOGGER = get_logger(name="docdate-weekday-evidence")
RESULTS_DIR = "test/results"
RESULTS_PATH = Path(RESULTS_DIR) / "docdate-weekday-evidence.csv"

# Current-data baseline for impossible weekday/date evidence occurrences.
# Later OCR and docDate curation PRs should ratchet this down.
MAX_INVALID_WEEKDAY_DATE_EVIDENCE = 3611

SWEDISH_WEEKDAYS = (
    "måndag",
    "tisdag",
    "onsdag",
    "torsdag",
    "fredag",
    "lördag",
    "söndag",
)

WEEKDAY_DATE_PATTERN = re.compile(
    r"\b"
    r"(?P<weekday>[^\W\d_]*dag(?:en)?)"
    r"\s+den\s+"
    r"(?P<date_text>"
    r"(?P<day>\d{1,2})\.?\s+"
    r"[^\W\d_]{3,}"
    r"(?:\s+(?P<year>\d{4})(?!\d))?"
    r")"
    r"\b"
    r"(?(year)|(?!\s+\d))",
    re.IGNORECASE,
)

_WEEKDAY_DATE_EVIDENCE_ERRORS = None


def normalized_text(element):
    """Return whitespace-normalized text content for one parsed TEI element."""
    return " ".join(" ".join(element.itertext()).split())


def normalized_weekday(weekday):
    """Return the Swedish weekday base form used by date.weekday()."""
    weekday = weekday.lower()
    if weekday.endswith("en"):
        return weekday[:-2]
    return weekday


def parse_swedish_date(text, expected_year, expected_day):
    """Parse one Swedish day-month-year expression as a date."""
    parsed = dateparser.parse(
        text,
        languages=["sv"],
        date_formats=("%d %B %Y", "%d. %B %Y"),
        settings={
            "STRICT_PARSING": True,
            "RETURN_AS_TIMEZONE_AWARE": False,
        },
    )
    if parsed is None:
        return None
    parsed_date = parsed.date()
    if parsed_date.year != expected_year:
        return None
    if parsed_date.day != expected_day:
        return None
    return parsed_date


def inferred_header_year(metadata, month, explicit_year):
    """Infer a year for yearless headings from protocol metadata."""
    if explicit_year is not None:
        return int(explicit_year), "explicit_year"

    secondary_year = metadata.get("secondary_year")
    if secondary_year is not None and month <= 6:
        return secondary_year, "secondary_year"

    return metadata["year"], "metadata_year"


def collect_weekday_date_evidence_errors():
    errors = []
    evidence_count = 0
    protocols = sorted(corpus_iterator("records", corpus_root="data"))
    LOGGER.info("Checking weekday/date evidence for %s protocols", len(protocols))

    for path in tqdm.tqdm(protocols):
        metadata = infer_metadata(path)
        root, namespaces = parse_tei(path)
        _, docdates = get_doc_dates(root)
        docdate_set = set(docdates)
        xml_id = f"{namespaces['xml_ns']}id"

        for note in root.xpath(
            ".//tei:body//tei:note",
            namespaces={"tei": namespaces["tei_ns"].strip("{}")},
        ):
            text = normalized_text(note)
            for match in WEEKDAY_DATE_PATTERN.finditer(text):
                weekday = normalized_weekday(match.group("weekday"))
                if weekday not in SWEDISH_WEEKDAYS:
                    continue

                date_text = match.group("date_text")
                explicit_year = match.group("year")
                day = int(match.group("day"))
                if explicit_year is None:
                    # Use a dummy year only to let dateparser identify the month;
                    # the actual year is inferred from protocol metadata below.
                    probe_date = parse_swedish_date(f"{date_text} 2000", 2000, day)
                    if probe_date is None:
                        continue
                    year, year_source = inferred_header_year(
                        metadata,
                        probe_date.month,
                        explicit_year,
                    )
                    observed_date = parse_swedish_date(
                        f"{date_text} {year}",
                        year,
                        day,
                    )
                else:
                    year_source = "explicit_year"
                    observed_date = parse_swedish_date(
                        date_text,
                        int(explicit_year),
                        day,
                    )

                if observed_date is None:
                    continue

                evidence_count += 1
                actual_weekday_index = observed_date.weekday()
                actual_weekday = SWEDISH_WEEKDAYS[actual_weekday_index]
                if actual_weekday == weekday:
                    continue

                observed_iso = observed_date.isoformat()
                docdate_support = observed_iso in docdate_set
                errors.append(
                    {
                        "file": path,
                        "source_line": note.sourceline,
                        "note_id": note.get(xml_id),
                        "matched_text": match.group(0),
                        "context": text[:240],
                        "observed_date": observed_date,
                        "claimed_weekday": weekday,
                        "actual_weekday": actual_weekday,
                        "year_source": year_source,
                        "docdate_support": docdate_support,
                    }
                )

    LOGGER.info(
        "Validated %s weekday/date evidence occurrence(s); found %s impossible occurrence(s)",
        evidence_count,
        len(errors),
    )
    if not errors:
        return pl.DataFrame()

    df = pl.DataFrame(errors)
    df = df.sort(["file", "source_line", "observed_date", "matched_text"])
    os.makedirs(RESULTS_DIR, exist_ok=True)
    df.write_csv(str(RESULTS_PATH))
    return df


def weekday_date_evidence_errors():
    global _WEEKDAY_DATE_EVIDENCE_ERRORS

    if _WEEKDAY_DATE_EVIDENCE_ERRORS is None:
        _WEEKDAY_DATE_EVIDENCE_ERRORS = collect_weekday_date_evidence_errors()
    return _WEEKDAY_DATE_EVIDENCE_ERRORS


class TestDocDateWeekdayEvidence(unittest.TestCase):
    def test_weekday_date_evidence_matches_calendar(self):
        """Guarantee: Swedish weekday/date evidence should match the calendar.

        Why this matters: impossible weekday/date pairs identify either false
        date evidence that may have polluted ``docDate`` metadata, or OCR errors
        in printed sitting headings and running headers that should be curated
        separately.

        Data: parsed TEI body ``note`` text from every protocol in ``data/``.
        Only clear Swedish weekday/date expressions are checked; OCR-distorted
        month names and non-header date mentions without weekdays are outside
        this minimal guarantee.
        """
        df_invalid = weekday_date_evidence_errors()
        self.assertLessEqual(
            len(df_invalid),
            MAX_INVALID_WEEKDAY_DATE_EVIDENCE,
            (
                f"{len(df_invalid)} impossible weekday/date evidence occurrence(s), "
                f"exceeding baseline {MAX_INVALID_WEEKDAY_DATE_EVIDENCE}; see {RESULTS_PATH}"
            ),
        )


if __name__ == "__main__":
    unittest.main()
