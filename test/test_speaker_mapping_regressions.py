import unittest
import xml.etree.ElementTree as ET


TEI_NS = "http://www.tei-c.org/ns/1.0"


def tei_tag(local_name):
    return f"{{{TEI_NS}}}{local_name}"


class SpeakerMappingRegressionTest(unittest.TestCase):
    def test_prime_minister_sandler_speeches_use_sandler_person_id(self):
        """Verify that Sandler's 1926 prime minister speeches map to Sandler."""
        sandler_id = "i-9iqLBgdAYEoR244dkazyYj"
        schlyter_id = "i-NdmzAJFCHr1sfnsvdVwR4y"
        target_intro = "Hans excellens herr statsministern Sandler:"
        path = "data/1926/prot-1926--ak--044.xml"

        tree = ET.parse(path)
        sandler_speeches = []
        last_speaker_intro = ""

        for body in tree.findall(f".//{tei_tag('body')}"):
            for div in body.findall(tei_tag("div")):
                for elem in div:
                    if elem.tag == tei_tag("note") and elem.attrib.get("type") == "speaker":
                        last_speaker_intro = "".join(elem.itertext()).strip()
                    elif elem.tag == tei_tag("u") and last_speaker_intro == target_intro:
                        sandler_speeches.append(elem.attrib.get("who"))

        self.assertGreater(
            len(sandler_speeches),
            0,
            f"Expected to find speeches after speaker intro {target_intro!r} in {path}",
        )
        self.assertNotIn(
            schlyter_id,
            sandler_speeches,
            f"Sandler speeches in {path} should not map to Schlyter "
            f"({schlyter_id}); found {sandler_speeches}",
        )
        self.assertTrue(
            all(who == sandler_id for who in sandler_speeches),
            f"Sandler speeches in {path} should all map to Sandler "
            f"({sandler_id}); found {sandler_speeches}",
        )


if __name__ == "__main__":
    unittest.main()
