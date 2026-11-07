"""
Data integrity test for weekday/date evidence in protocol body notes.

The records corpus often stores printed sitting headings and running headers as
short TEI ``note`` elements in the protocol body.  This test extracts clear
Swedish weekday/date evidence of the form ``Tisdagen den 7 oktober`` or
``Tisdagen den 7 oktober 1986`` from parsed note text and checks that the named
weekday matches the calendar date.

Only mismatches in notes annotated as ``type="date"`` count towards the
release limit, because those notes can be used for metadata extraction.
Mismatches in other notes are included in the diagnostics for OCR review.
"""
from functools import lru_cache
from pathlib import Path
import re
import unittest

from dateparser.search import search_dates
import polars as pl
import tqdm

from pyriksdagen.io import parse_tei
from pyriksdagen.utils import corpus_iterator, get_doc_dates, infer_metadata
from trainerlog import get_logger


LOGGER = get_logger(name="docdate-weekday-evidence")
RESULTS_PATH = Path("test/results/docdate-weekday-evidence.csv")

# On records dev 8300769e13 with dateparser 1.2.2, 2,942 mismatches
# were in annotated date notes. Later curation should lower this limit.
MAX_INVALID_DATE_NOTE_EVIDENCE = 2942

SWEDISH_WEEKDAYS = (
    "måndag",
    "tisdag",
    "onsdag",
    "torsdag",
    "fredag",
    "lördag",
    "söndag",
)

# If digits follow the month after whitespace, require a four-digit year.
WEEKDAY_DATE_PATTERN = re.compile(
    r"\b(?P<weekday>[^\W\d_]*dag)(?:en)?\s+den\s+"
    r"(?P<date_text>(?P<day>\d{1,2})\.?\s+[^\W\d_]{3,}"
    r"(?:\s+(?P<year>\d{4})|(?!\s+\d)))\b",
    re.IGNORECASE,
)

class TestDocDateWeekdayEvidence(unittest.TestCase):
    def normalized_text(self, element):
        """Return whitespace-normalized text content for one parsed TEI element."""
        return " ".join(" ".join(element.itertext()).split())

    @staticmethod
    @lru_cache(maxsize=8192)
    def parse_swedish_date(text, expected_year, expected_day):
        """Parse one Swedish day-month-year expression as a date."""
        # Printed running headers repeat dates; avoid parsing each occurrence again.
        # The extracted phrase may have a dot after the day, which search_dates skips.
        phrase = text.replace(".", "", 1)
        matches = search_dates(
            phrase,
            languages=["sv"],
            settings={"STRICT_PARSING": True},
        )
        if not matches or len(matches) != 1:
            return None
        matched_text, parsed = matches[0]
        if matched_text != phrase:
            return None
        parsed_date = parsed.date()
        if parsed_date.year != expected_year:
            return None
        if parsed_date.day != expected_day:
            return None
        return parsed_date

    def inferred_header_year(self, metadata, month, explicit_year):
        """Infer a year for yearless headings from protocol metadata."""
        if explicit_year is not None:
            return int(explicit_year), "explicit_year"

        secondary_year = metadata.get("secondary_year")
        if secondary_year is not None and month <= 6:
            return secondary_year, "secondary_year"

        return metadata["year"], "metadata_year"

    def collect_weekday_date_evidence_errors(self):
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
                text = self.normalized_text(note)
                for match in WEEKDAY_DATE_PATTERN.finditer(text):
                    weekday = match.group("weekday").lower()
                    if weekday not in SWEDISH_WEEKDAYS:
                        continue

                    date_text = match.group("date_text")
                    explicit_year = match.group("year")
                    day = int(match.group("day"))
                    if explicit_year is None:
                        # Use a dummy year only to let dateparser identify the month;
                        # the actual year is inferred from protocol metadata below.
                        probe_date = self.parse_swedish_date(
                            f"{date_text} 2000",
                            2000,
                            day,
                        )
                        if probe_date is None:
                            continue
                        year, year_source = self.inferred_header_year(
                            metadata,
                            probe_date.month,
                            explicit_year,
                        )
                        observed_date = self.parse_swedish_date(
                            f"{date_text} {year}",
                            year,
                            day,
                        )
                    else:
                        year_source = "explicit_year"
                        observed_date = self.parse_swedish_date(
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
                            "note_type": note.get("type"),
                        }
                    )

        LOGGER.info(
            "Validated %s weekday/date evidence occurrence(s); found %s impossible occurrence(s)",
            evidence_count,
            len(errors),
        )
        if not errors:
            return pl.DataFrame()

        df = pl.DataFrame(errors, schema_overrides={"note_id": pl.String, "note_type": pl.String})
        df = df.sort(["file", "source_line", "observed_date", "matched_text"])
        RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
        df.write_csv(RESULTS_PATH)
        return df

    def test_annotated_date_notes_match_calendar(self):
        """Guarantee: weekday/date mismatches in annotated date notes stay within the limit.

        Counted unit: one parsed weekday/date expression in a TEI body
        ``note`` with ``type="date"``. Other note mismatches are diagnostic only.
        """
        df_invalid = self.collect_weekday_date_evidence_errors()
        failures = (
            0 if df_invalid.is_empty()
            else df_invalid.filter(pl.col("note_type") == "date").height
        )
        LOGGER.info(
            "%s mismatches in annotated date notes; %s diagnostic-only mismatches",
            failures,
            df_invalid.height - failures,
        )
        self.assertLessEqual(
            failures,
            MAX_INVALID_DATE_NOTE_EVIDENCE,
            (
                f"{failures} weekday/date mismatches in annotated date notes, "
                f"exceeding baseline {MAX_INVALID_DATE_NOTE_EVIDENCE}; see {RESULTS_PATH}"
            ),
        )


if __name__ == "__main__":
    unittest.main()
