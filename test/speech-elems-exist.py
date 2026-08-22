#!/usr/bin/env python3
from glob import glob
from pyriksdagen.io import parse_tei
from tqdm import tqdm
from trainerlog import get_logger
import json
import unittest




logger = get_logger(name="Trainer Log")




class Test(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.records = sorted(glob("data/*/*.xml"))
        cls.phantom_speech_elements = {}


    @classmethod
    def tearDownClass(cls):
        if len(cls.phantom_speech_elements) > 0:
            with open("test/results/phantom_speech_elements.json", "w+") as outf:
                json.dump(cls.phantom_speech_elements, outf, ensure_ascii=False, indent=4)
            logger.warn("Not all speech elements are accounted for. Test fails")
        try:
            assert len(cls.phantom_speech_elements) == 0
            logger.info("Test passes.")
        except:
            logger.critical("Test fails")




    def test_not_phantom_speech_elems(self):
        """
        Check that all speech elements listed under the constitution
        element actually exist in the record.
        """
        for record in tqdm(self.records):
            speech_elems = []
            root, ns = parse_tei(record)

            speeches = root.findall(f".//{ns['tei_ns']}composition/{ns['tei_ns']}note[@type=\"speech\"]")
            if len(speeches) == 0:
                continue
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
                    if record not in self.phantom_speech_elements:
                        self.phantom_speech_elements[record] = []
                    self.phantom_speech_elements[record].append(se)
                    logger.warn(f"{record} : {se} not found")
                    logger.warn(ns)




if __name__ == '__main__':
    unittest.main()
