#!/usr/bin/env python3
"""
Check that all elements with text have IDs.
    - <u> is the oddball, no text (according to lxml), but we want it IDed
    - test checks cannonical elems : seg, u, and note for ID
    - and any other elem with text (elem.text != None or '')
"""
from lxml import etree
from pyriksdagen.utils import elem_iter, protocol_iterators
from tqdm import tqdm
from trainerlog import get_logger
import pandas as pd
import unittest


logger = get_logger(name="paragraph-has-id")



class Test(unittest.TestCase):


    def count_missing_ids(self, protocol, counter, fails):
        tei_ns = "{http://www.tei-c.org/ns/1.0}"
        xml_ns = "{http://www.w3.org/XML/1998/namespace}"
        canonical_tags = [f'{tei_ns}u', 'u', f'{tei_ns}note', f'{tei_ns}seg']
        parser = etree.XMLParser(remove_blank_text=True)
        root = etree.parse(protocol, parser).getroot()
        if root.tag == f"{tei_ns}TEI":
            if f'{xml_ns}id' not in root.attrib:
                counter += 1
                fails.append([protocol, "no TEI ID attr", 0])
        else:
            logger.error(f"Unexpected root element in {protocol}: {root.tag}")
        for body in root.findall(".//" + tei_ns + "body"):
            for div in body.findall(tei_ns + "div"):
                for elem in div.iter():
                    if elem.tag in canonical_tags or (elem.text and len(elem.text) > 0):
                        if f'{xml_ns}id' not in elem.attrib:
                            counter += 1
                            fails.append([protocol, "no ID attr", elem.sourceline])
                        elif elem.attrib[f'{xml_ns}id'] == None or elem.attrib[f'{xml_ns}id'] == '':
                            # the parser will fail on the above line, so we should never get here.
                            counter += 1
                            fails.append([protocol, "empty ID string or NoneType ", elem.sourceline])
        return counter, fails


    def test_p_has_id(self):
        counter = 0
        fails = []
        f_cols = ["protocol", 'reason', "line_nr"]
        protocols = sorted(list(protocol_iterators("data/", start=1867, end=2022)))
        for p in tqdm(protocols, total=len(protocols)):
            counter, fails = self.count_missing_ids(p, counter, fails)

        if counter > 0:
            fail_df = pd.DataFrame(fails, columns=f_cols)
            logger.error(f"{counter} text-bearing element(s) are missing xml:id attributes")
            logger.debug(fail_df.to_string())
        self.assertEqual(counter, 0, f"{counter} text-bearing element(s) are missing xml:id attributes")




if __name__ == '__main__':
    unittest.main()
