#!/usr/bin/env python3
"""
Regression tests for known speaker-introduction classification errors.
"""
from pathlib import Path
from pyriksdagen.io import parse_tei
import unittest


TEI_NS = "http://www.tei-c.org/ns/1.0"
XML_NS = "http://www.w3.org/XML/1998/namespace"
NS = {"tei": TEI_NS, "xml": XML_NS}


class TestSpeakerIntroductionRegressions(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.record_path = Path("data/1966/prot-1966--ak--030.xml")
        cls.root, _ = parse_tei(str(cls.record_path))

    def test_erlander_quote_is_not_speaker_intro(self):
        """
        Check that the quoted Erlander lead-in is not tagged as a speaker introduction.
        """
        speaker_notes = self.root.xpath(
            ".//tei:note[@type='speaker']",
            namespaces=NS,
        )
        speaker_texts = [
            "".join(note.itertext()).strip()
            for note in speaker_notes
        ]

        self.assertNotIn(
            "Herr Erlander säger nu:",
            speaker_texts,
            "The quote lead-in 'Herr Erlander säger nu:' must remain speech text, not a speaker introduction.",
        )

    def test_erlander_quote_remains_in_ohlin_utterance(self):
        """
        Check that the quoted Erlander passage remains attributed to Bertil Ohlin.
        """
        ohlin_id = "i-BqDGKscaLhUZHhaFFmx5pf"
        quote_seg = self.root.xpath(
            ".//tei:seg[@xml:id='i-7hGHVsfQzkYYGCL9qnGK9f']",
            namespaces=NS,
        )

        self.assertEqual(
            len(quote_seg),
            1,
            "Expected exactly one segment with xml:id='i-7hGHVsfQzkYYGCL9qnGK9f'.",
        )
        self.assertEqual(
            "".join(quote_seg[0].itertext()).strip(),
            "Herr Erlander säger nu:",
            "The regression segment text has changed unexpectedly.",
        )
        self.assertEqual(
            quote_seg[0].getparent().attrib["who"],
            ohlin_id,
            "The quote lead-in segment must be inside an utterance attributed to Bertil Ohlin.",
        )

        for utterance_id in [
            "i-80f462bca193d8a9-24",
            "i-bcf7761ce2d77b36-0",
            "i-bcf7761ce2d77b36-1",
        ]:
            utterance = self.root.xpath(
                f".//tei:u[@xml:id='{utterance_id}']",
                namespaces=NS,
            )
            self.assertEqual(
                len(utterance),
                1,
                f"Expected exactly one utterance with xml:id='{utterance_id}'.",
            )
            self.assertEqual(
                utterance[0].attrib["who"],
                ohlin_id,
                f"Utterance '{utterance_id}' must be attributed to Bertil Ohlin.",
            )

        first = self.root.xpath(
            ".//tei:u[@xml:id='i-80f462bca193d8a9-24']",
            namespaces=NS,
        )[0]
        second = self.root.xpath(
            ".//tei:u[@xml:id='i-bcf7761ce2d77b36-0']",
            namespaces=NS,
        )[0]
        third = self.root.xpath(
            ".//tei:u[@xml:id='i-bcf7761ce2d77b36-1']",
            namespaces=NS,
        )[0]

        self.assertEqual(
            first.attrib.get("next"),
            second.attrib[f"{{{XML_NS}}}id"],
            "The first Ohlin utterance must point to the quoted continuation with its next attribute.",
        )
        self.assertEqual(
            second.attrib.get("prev"),
            first.attrib[f"{{{XML_NS}}}id"],
            "The quoted continuation must point back to the preceding Ohlin utterance with its prev attribute.",
        )
        self.assertEqual(
            second.attrib.get("next"),
            third.attrib[f"{{{XML_NS}}}id"],
            "The quoted continuation must point to the following page continuation with its next attribute.",
        )
        self.assertEqual(
            third.attrib.get("prev"),
            second.attrib[f"{{{XML_NS}}}id"],
            "The following page continuation must point back to the quoted continuation with its prev attribute.",
        )


if __name__ == "__main__":
    unittest.main()
