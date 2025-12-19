#!/usr/bin/env python3
from glob import glob
from pyriksdagen.io import parse_tei
from pyriksdagen.utils import corpus_iterator
from tqdm import tqdm
from trainerlog import get_logger
import json
import unittest




logger = get_logger("next-prev-logger")




class Test(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.records = sorted(glob("data/*/*.xml"))
        cls.incoherant_records = {}


    @classmethod
    def tearDownClass(cls):
        if len(cls.incoherant_records) > 0:
            with open("test/results/incoherant-next-prev.json", "w+") as outf:
                json.dump(cls.incoherant_records, outf, indent=2, ensure_ascii=False)
            raise Exception(f"{len(cls.incoherant_records)} records have incoherent 'next'/'prev' tagging")


    def check_next_prev_coherence(self, record):
        """
        Check that:
            a) all 'next' attributes point to next <u> element
            b) all 'prev' attributes point to previous <u> element
        """
        def add_to_d(elem, type_, problem_id):
            if record not in self.incoherant_records:
                self.incoherant_records[record] = []
            self.incoherant_records[record].append([elem, type_, problem_id])

        next_attrib = None
        prev_id = None
        root, ns = parse_tei(record)
        for body in root.findall(f".//{ns['tei_ns']}body"):
            for elem in root.findall(f".//{ns['tei_ns']}u"):
                #for elem in div:
                    if elem.tag == f"{ns['tei_ns']}u":

                        elem_id = elem.attrib[f"{ns['xml_ns']}id"]
                        if next_attrib is not None:
                            if next_attrib != elem_id:
                                logger.warn(f"incoherent next in {record}: {next_attrib} {elem_id}")
                                add_to_d(elem_id, "next", next_attrib)
                                return False

                        next_attrib = elem.attrib.get("next")

                        if "prev" in elem.attrib:
                            if prev_id != elem.attrib["prev"]:
                                logger.warn(f"incoherent prev in {record}: {next_attrib} {elem.attrib['prev']}")
                                add_to_d(elem_id, "prev", elem.attrib["prev"])
                                return False

                        prev_id = elem_id
        return True


    def test_next_prev(self):
        for record in tqdm(self.records):
            self.check_next_prev_coherence(record)






if __name__ == '__main__':
    unittest.main()
