#!/usr/bin/env python3
from glob import glob
from pyriksdagen.io import parse_tei
from tqdm import tqdm
from trainerlog import get_logger
import json
import unittest




logger = get_logger(name="test-speech-elems-exist")




class Test(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.records = sorted(glob("data/*/*.xml"))

    def test_not_phantom_speech_elems(self):
        phantom_speech_elements = {}

        no_records = len(self.records)
        records_w_no_speeches = 0
        for record in tqdm(self.records):
            speech_elems = []
            root, ns = parse_tei(record)
            speeches = root.findall(f".//{ns['tei_ns']}constitution/{ns['tei_ns']}note[@type=\"speech\"]")
            if len(speeches) == 0:
                logger.warning(f"No speeches found in {record}")
                records_w_no_speeches += 1
            else:
                for speech in speeches:
                    u_elems = speech.findall(f"{ns['tei_ns']}linkGrp[@type=\"u\"]/{ns['tei_ns']}ptr")
                    try:
                        assert len(u_elems) > 0
                    except:
                        raise ValueError("A speech can't have no u elements")
                    for u_elem in u_elems:
                        speech_elems.append(f"{u_elem.attrib['target'][1:]}")
                for se in speech_elems:
                    if not root.xpath(
                            f"boolean(.//tei:u[@xml:id=\"{se}\"])",
                            namespaces={"tei": ns["tei_ns"][1:-1], "xml": ns["xml_ns"][1:-1]}):
                        if record not in phantom_speech_elements:
                            phantom_speech_elements[record] = []
                        phantom_speech_elements[record].append(se)

            if record in phantom_speech_elements:
                missing_elems = phantom_speech_elements[record]
                missing_elems = ", ".join(missing_elems)
                if len(missing_elems) > 300:
                    missing_elems = missing_elems[:200] + " [...] " + missing_elems[-50:]
                logger.error(f"{record} : the following elements: {missing_elems} not found")

            self.assertGreaterEqual(no_records * 0.2, records_w_no_speeches, f"Less than 20% of records should have no speeches ({records_w_no_speeches} found)")

        if len(phantom_speech_elements) > 0:
            with open("test/results/phantom_speech_elements.json", "w+") as outf:
                json.dump(phantom_speech_elements, outf, ensure_ascii=False, indent=4)
            logger.warn("Not all speech elements are accounted for. Test fails")
        
        no_errors = len(phantom_speech_elements)
        self.assertEqual(0, no_errors, f"Phantom speech elements detected in {no_errors} records")



if __name__ == '__main__':
    unittest.main()
