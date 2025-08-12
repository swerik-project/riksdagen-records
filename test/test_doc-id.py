#!/usr/bin/env python3
"""
Check that:

    - each document has an ID in the TEI element
    - ID matches the doc filename
    - URL links in the pb element use the same ID

"""
from glob import glob
from lxml import etree
from pyriksdagen.io import parse_tei
from tqdm import tqdm
import pandas as pd
import unittest, warnings




class DocIdTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        """
        set global variables for all test cases
        """
        super(DocIdTests, cls).setUpClass()
        cls.records = sorted(glob("data/*/*.xml"))
        cls.no_id = []
        cls.id_not_fn = []
        cls.id_facs_mismatch = []


    @classmethod
    def tearDownClass(cls):
        """
        Write summary output when appropriate
        """
        print("\nDocs with no ID:", cls.no_id[:5], "\n", len(cls.no_id), "instances")
        if len(cls.no_id) > 0:
            pd.DataFrame(cls.no_id, columns=["record", "problem"]).to_csv("test/results/doc-wout-id.tsv", sep="\t", index=False)
        print("\nDocs with ID / FN mismatch", cls.id_not_fn[:5], "\n", len(cls.id_not_fn), "instances")
        if len(cls.id_not_fn) > 0:
            pd.DataFrame(cls.id_not_fn, columns=["record", "ID", "filename"]).to_csv("test/results/id-not-filename.tsv", sep="\t", index=False)
        print("\nDocs with ID / FACS mismatch", cls.id_facs_mismatch[:5], "\n", len(cls.id_facs_mismatch), "instances")
        if len(cls.id_facs_mismatch) > 0:
            pd.DataFrame(cls.id_facs_mismatch, columns=["record", "facs",  "problem"]).to_csv("test/results/id-not-facs.tsv", sep="\t", index=False)


    def test_doc_has_id(self):
        """
        test each document has an ID in the tei element
        """
        for record in tqdm(self.records[:10]):
            root, ns = parse_tei(record)
            if f"{ns['xml_ns']}id" not in root.attrib:
                self.no_id.append([record, "no ID attrib"])


    def test_doc_id_is_filename(self):
        """
        test each doc ID == its filename (less extension)
        """
        for record in tqdm(self.records[:10]):
            root, ns = parse_tei(record)
            if f"{ns['xml_ns']}id" not in root.attrib:
                print("no ID...skipping")
            else:
                ID = root.attrib[f"{ns['xml_ns']}id"]
                FN = record.split('/')[-1][:-4]
                if not ID == FN:
                    self.id_not_fn.append([record, ID, FN])


    def test_doc_id_in_dacs(self):
        """
        test that doc ID matches the corresponding elements in the pb elements' facs attribute
        """
        for record in tqdm(self.records[:10]):
            root, ns = parse_tei(record)
            if f"{ns['xml_ns']}id" not in root.attrib:
                print("no ID...skipping")
            else:
                ID = root.attrib[f"{ns['xml_ns']}id"]
                pbs = root.findall(f".//{ns['tei_ns']}pb")
                for pb in pbs:
                    facs = pb.attrib["facs"]
                    if len(facs) == 0:
                        self.id_facs_mismatch.append([record, facs, "no facs"])
                    else:
                        s = facs.split('/')
                        page = s[-1]
                        doc = s[-2]
                        if doc != ID:
                            self.id_facs_mismatch.append([record, facs, "facs not ID"])
                        else:
                            print("facs problem 1")
                        if "_".join(page.split("_")[:-1]) != ID:
                            self.id_facs_mismatch.append([record, facs, "facs not page"])



if __name__ == '__main__':
    unittest.main()
