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
MAX_INVALID_WEEKDAY_DATE_EVIDENCE = 4534

TEI_NS = {"tei": "http://www.tei-c.org/ns/1.0"}
XML_ID = "{http://www.w3.org/XML/1998/namespace}id"

SWEDISH_WEEKDAYS = (
    "måndag",
    "tisdag",
    "onsdag",
    "torsdag",
    "fredag",
    "lördag",
    "söndag",
)

SWEDISH_MONTHS = {
    "januari": 1,
    "februari": 2,
    "mars": 3,
    "april": 4,
    "maj": 5,
    "juni": 6,
    "juli": 7,
    "augusti": 8,
    "september": 9,
    "oktober": 10,
    "november": 11,
    "december": 12,
}

WEEKDAY_DATE_PATTERN = re.compile(
    r"(?i)\b"
    r"(?P<weekday>måndagen|tisdagen|onsdagen|torsdagen|fredagen|lördagen|söndagen)"
    r"\s+den\s+"
    r"(?P<day>\d{1,2})\.?\s+"
    r"(?P<month>januari|februari|mars|april|maj|juni|juli|augusti|september|oktober|november|december)"
    r"\b(?:\s+(?P<year>\d{4}))?"
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

def inferred_header_year(path, metadata, month, explicit_year):
    """Infer a year for yearless headings from the protocol folder."""
    if explicit_year is not None:
        return int(explicit_year), "explicit_year"

    folder = Path(path).parts[1]
    if len(folder) == 6 and folder.isdigit():
        if month >= 7:
            return metadata["year"], "folder_start_year"
        return metadata["secondary_year"], "folder_end_year"

    return metadata["year"], "metadata_year"


def collect_weekday_date_evidence_errors():
    errors = []
    evidence_count = 0
    protocols = sorted(corpus_iterator("records", corpus_root="data"))
    LOGGER.info("Checking weekday/date evidence for %s protocols", len(protocols))

    for path in tqdm.tqdm(protocols):
        metadata = infer_metadata(path)
        root, _ = parse_tei(path)
        _, docdates = get_doc_dates(root)
        docdate_set = set(docdates)

        for note in root.xpath(".//tei:body//tei:note", namespaces=TEI_NS):
            text = normalized_text(note)
            for match in WEEKDAY_DATE_PATTERN.finditer(text):
                weekday = normalized_weekday(match.group("weekday"))
                month = SWEDISH_MONTHS[match.group("month").lower()]
                year, year_source = inferred_header_year(
                    path,
                    metadata,
                    month,
                    match.group("year"),
                )

                try:
                    observed_date = date(year, month, int(match.group("day")))
                except ValueError:
                    continue

                evidence_count += 1
                actual_weekday_index = observed_date.weekday()
                actual_weekday = SWEDISH_WEEKDAYS[actual_weekday_index]
                if actual_weekday == weekday:
                    continue

                observed_iso = observed_date.isoformat()
                docdate_support = observed_iso in docdate_set
                error_type = (
                    "invalid_weekday_supports_docdate"
                    if docdate_support
                    else "invalid_weekday_not_in_docdate"
                )
                errors.append(
                    {
                        "file": str(path),
                        "error_type": error_type,
                        "issue": "weekday/date evidence does not match calendar",
                        "source_line": note.sourceline,
                        "note_id": note.get(XML_ID),
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
