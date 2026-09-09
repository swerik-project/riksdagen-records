import unittest
import xml.etree.ElementTree as ET


TEI_NS = {"tei": "http://www.tei-c.org/ns/1.0"}


class DocDateFilenameTest(unittest.TestCase):
    def test_docdates_include_dates_from_protocol_filename(self):
        """Verify that selected protocols expose their filename date in docDate."""
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
                self.assertIn(
                    expected_date,
                    docdates,
                    f"{path} should include docDate @when={expected_date}; "
                    f"found {sorted(docdates)}",
                )


if __name__ == "__main__":
    unittest.main()
