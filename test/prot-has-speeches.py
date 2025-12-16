#!/usr/bin/env python3
from glob import glob
from pyriksdagen.io import parse_tei
from tqdm import tqdm
from trainerlog import get_logger
import unittest




logger = get_logger(name="Trainer Log")




class Test(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.records = sorted(glob("data/*/*.xml"))
        cls.records_without_speeches = []


    @classmethod
    def tearDownClass(cls):
        if len(cls.records_without_speeches) > 0:
            with open("test/results/records_without_speeches.txt", "w+") as outf:
                [outf.write(f"{r}\n") for r in cls.records_without_speeches]
        logger.info(f"There are {len(cls.records_without_speeches)} records (of {len(cls.records)}) without annotated speeches.")




    def test_record_has_speeches(self):
        for record in tqdm(self.records):
            root, ns = parse_tei(record)
            speeches = root.findall(f".//{ns['tei_ns']}composition/{ns['tei_ns']}note[@type=\"speech\"]")
            if len(speeches) == 0:
                self.records_without_speeches.append(record)




if __name__ == '__main__':
    unittest.main()
