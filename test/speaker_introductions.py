#!/usr/bin/env python3
"""
Regression tests for known speaker-introduction classification errors.
"""
from pathlib import Path
from lxml import etree
import unittest


TEI_NS = "http://www.tei-c.org/ns/1.0"
XML_NS = "http://www.w3.org/XML/1998/namespace"
NS = {"tei": TEI_NS, "xml": XML_NS}


class TestSpeakerIntroductionRegressions(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        parser = etree.XMLParser(remove_blank_text=True)
        cls.record_path = Path("data/1966/prot-1966--ak--030.xml")
        cls.root = etree.parse(str(cls.record_path), parser).getroot()

    def test_erlander_quote_is_not_speaker_intro(self):
        speaker_notes = self.root.xpath(
            ".//tei:note[@type='speaker']",
            namespaces=NS,
        )
        speaker_texts = [
            "".join(note.itertext()).strip()
            for note in speaker_notes
        ]

        self.assertNotIn("Herr Erlander säger nu:", speaker_texts)

    def test_erlander_quote_remains_in_ohlin_utterance(self):
        ohlin_id = "i-BqDGKscaLhUZHhaFFmx5pf"
        quote_seg = self.root.xpath(
            ".//tei:seg[@xml:id='i-7hGHVsfQzkYYGCL9qnGK9f']",
            namespaces=NS,
        )

        self.assertEqual(len(quote_seg), 1)
        self.assertEqual("".join(quote_seg[0].itertext()).strip(), "Herr Erlander säger nu:")
        self.assertEqual(quote_seg[0].getparent().attrib["who"], ohlin_id)

        for utterance_id in [
            "i-80f462bca193d8a9-24",
            "i-bcf7761ce2d77b36-0",
            "i-bcf7761ce2d77b36-1",
        ]:
            utterance = self.root.xpath(
                f".//tei:u[@xml:id='{utterance_id}']",
                namespaces=NS,
            )
            self.assertEqual(len(utterance), 1)
            self.assertEqual(utterance[0].attrib["who"], ohlin_id)

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

        self.assertEqual(first.attrib.get("next"), second.attrib[f"{{{XML_NS}}}id"])
        self.assertEqual(second.attrib.get("prev"), first.attrib[f"{{{XML_NS}}}id"])
        self.assertEqual(second.attrib.get("next"), third.attrib[f"{{{XML_NS}}}id"])
        self.assertEqual(third.attrib.get("prev"), second.attrib[f"{{{XML_NS}}}id"])


if __name__ == "__main__":
    unittest.main()
