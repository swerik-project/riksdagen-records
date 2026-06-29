#!/usr/bin/env python3
"""
Test there are no empty speeches.
"""
from pytest_cfg_fetcher.fetch import fetch_config
from datetime import datetime
from lxml import etree
from pyriksdagen.utils import (
    parse_protocol,
    protocol_iterators,
)
from tqdm import tqdm
from trainerlog import get_logger
import pandas as pd
import unittest


logger = get_logger(name="empty-speech")



class Test(unittest.TestCase):

    def test_no_empty_speech(self):
        """
        Test protocol has no empty `u` or `seg` elements
        """
        rows = []
        protocols = sorted(list(protocol_iterators("data",
                                                   start=1867,
                                                   end=2022)))
        for p in tqdm(protocols, total=len(protocols)):
            root, ns = parse_protocol(p, get_ns=True)
            for elem in root.iter(f'{ns["tei_ns"]}u'):
                if len(elem) == 0:
                    if f'{ns["xml_ns"]}id' in elem.attrib:
                        u_id = elem.attrib[f'{ns["xml_ns"]}id']
                        rows.append([p, "u", u_id])
                        logger.error(f"Empty u element: {p}, {u_id}")
                else:
                    for seg in elem:
                        if not seg.text or seg.text.strip() == '':
                            if f'{ns["xml_ns"]}id' in seg.attrib:
                                seg_id = seg.attrib[f'{ns["xml_ns"]}id']
                                rows.append([p, "seg", seg_id])
                                logger.error(f"Empty seg element: {p}, {seg_id}")
        if len(rows) > 0:
            config = fetch_config("empty-speech")
            if config and config["write_empty_speeches"]:
                now = datetime.now().strftime('%Y%m%d-%H%M%S')
                cols = ["protocol", "elem", "elem_id"]
                df = pd.DataFrame(rows, columns=cols)
                df.to_csv(
                    f"{config['test_out_path']}empty-speech_{now}.csv",
                    sep=';',
                    index=False)

            logger.debug(pd.DataFrame(rows, columns=["protocol", "elem", "elem_id"]).to_string())

        self.assertEqual(len(rows), 0, f"{len(rows)} empty speech element(s) found")




if __name__ == '__main__':
    unittest.main()
