"""
Test Protocols are not empty.
"""
from pyriksdagen.utils import (
    get_data_location,
    parse_protocol,
    protocol_iterators,
)
from tqdm import tqdm
import unittest
import warnings



class EmptyProtocol(Warning):

    def __init__(self, m):
        self.message = m

    def __str__(self):
        return self.message




class Test(unittest.TestCase):

    def test_not_empty(self):
        protocols = sorted(list(protocol_iterators('data')))
        empty = 0
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
                    warnings.warn(f"FAIL: {p}", EmptyProtocol)
            else:
                empty += 1
                warnings.warn(f"FAIL: {p}", EmptyProtocol)
        self.assertEqual(empty, 0)




if __name__ == '__main__':
    unittest.main()
