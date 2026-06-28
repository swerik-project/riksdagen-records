#!/usr/bin/env python3
"""
Test records are not obvious snabbprotokoll.
"""
from pathlib import Path
from lxml import etree
import os
import re
import unittest


DATA_DIR = Path("data")
DEFAULT_START_YEAR = 2000
START_YEAR_ENV = "SNABBPROTOKOLL_START_YEAR"
NS = {"tei": "http://www.tei-c.org/ns/1.0"}
SUSPECT_PATTERNS = [
    re.compile(r"\bsnabbprotokoll\w*\b", re.IGNORECASE),
    re.compile(r"\bprelimin[aä]rt\s+protokoll\w*\b", re.IGNORECASE),
]
DOCUMENT_LEVEL_FIELDS = {
    "header-title": ".//tei:teiHeader//tei:title",
    "header-idno": ".//tei:teiHeader//tei:idno",
    "header-class-code": ".//tei:teiHeader//tei:classCode",
    "front-head": ".//tei:text/tei:front//tei:head",
    "front-note": ".//tei:text/tei:front//tei:note",
    "front-paragraph": ".//tei:text/tei:front//tei:p",
}


class Test(unittest.TestCase):

    def _start_year(self):
        raw = os.environ.get(START_YEAR_ENV, str(DEFAULT_START_YEAR))
        try:
            return int(raw)
        except ValueError:
            self.fail(f"{START_YEAR_ENV} must be an integer, got {raw!r}")

    def _protocols_since(self, start_year):
        for year_dir in sorted(path for path in DATA_DIR.iterdir() if path.is_dir()):
            try:
                year = int(year_dir.name[:4])
            except ValueError:
                continue
            if year >= start_year:
                yield from sorted(year_dir.glob("*.xml"))

    def _field_texts(self, root):
        for label, xpath in DOCUMENT_LEVEL_FIELDS.items():
            for elem in root.xpath(xpath, namespaces=NS):
                text = " ".join(t.strip() for t in elem.itertext() if t.strip())
                if text:
                    yield label, text

    def _snippet(self, text, match):
        start = max(0, match.start() - 80)
        end = min(len(text), match.end() + 80)
        return text[start:end]

    def test_no_document_level_snabbprotokoll(self):
        """
        Checks that later records are not obvious snabbprotokoll/preliminary records.

        The default start year is 2000. Override it with SNABBPROTOKOLL_START_YEAR
        when older or newer ranges need to be checked.
        """
        suspicious = []
        for protocol in self._protocols_since(self._start_year()):
            root = etree.parse(str(protocol)).getroot()
            for label, text in self._field_texts(root):
                for pattern in SUSPECT_PATTERNS:
                    match = pattern.search(text)
                    if match:
                        suspicious.append(
                            f"{protocol} [{label}] {pattern.pattern}: {self._snippet(text, match)}"
                        )

        if suspicious:
            self.fail(
                "Found document-level snabbprotokoll/preliminary protocol markers:\n"
                + "\n".join(suspicious)
            )


if __name__ == "__main__":
    unittest.main()
