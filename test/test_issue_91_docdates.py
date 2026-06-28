import unittest
import xml.etree.ElementTree as ET


TEI_NS = {"tei": "http://www.tei-c.org/ns/1.0"}


class Issue91DocDateTest(unittest.TestCase):
    def test_filename_dates_are_present_in_docdate(self):
        expected_dates = {
            "data/1870/prot-1870--ak--0119.xml": "1870-01-19",
            "data/1870/prot-1870--ak--0401.xml": "1870-04-01",
            "data/1871/prot-1871--ak--0118.xml": "1871-01-18",
        }

        for path, expected_date in expected_dates.items():
            with self.subTest(path=path):
                tree = ET.parse(path)
                docdates = {
                    elem.attrib.get("when")
                    for elem in tree.findall(".//tei:docDate", TEI_NS)
                }
                self.assertIn(expected_date, docdates)


if __name__ == "__main__":
    unittest.main()
