"""
Test Protocols are not empty.
"""
from pyriksdagen.utils import (
    get_data_location,
    parse_protocol,
    protocol_iterators,
)
from tqdm import tqdm
from trainerlog import get_logger
import unittest


logger = get_logger(name="prot-not-empty")


class Test(unittest.TestCase):

    def test_not_empty(self):
        protocols = sorted(list(protocol_iterators('data')))
        empty = 0
        empty_protocols = []
        for p in tqdm(protocols):
            root, ns = parse_protocol(p, get_ns=True)
            divs = root.findall(f".//{ns['tei_ns']}div")
            notempty = False
            if len(divs) > 1:
                for div in divs:
                    if len(div) > 0:
                        notempty = True
                        continue
                if notempty == False:
                    empty += 1
                    empty_protocols.append(p)
                    logger.error(f"Empty protocol: {p}")
            else:
                empty += 1
                empty_protocols.append(p)
                logger.error(f"Protocol has no content divs: {p}")
        if empty_protocols:
            logger.debug(f"Empty protocols: {empty_protocols}")
        self.assertEqual(empty, 0, f"{empty} protocol(s) are empty or have no content divs")




if __name__ == '__main__':
    unittest.main()
