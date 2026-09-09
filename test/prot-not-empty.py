"""
Test that no records are empty.
"""
from pyriksdagen.utils import (
    get_data_location,
    parse_protocol,
    corpus_iterator,
)
from pyriksdagen.io import parse_tei
from tqdm import tqdm
from trainerlog import get_logger
import unittest


logger = get_logger(name="prot-not-empty")


class Test(unittest.TestCase):

    CURRENT_NO_EMPTY_RECORDS = 2
    def test_not_empty(self):
        """
        Test that zero records are empty, i.e. have no content divs or text content.
        """
        protocols = sorted(list(corpus_iterator('prot', corpus_root='data')))
        empty_count = 0
        empty_protocols = []
        for p in tqdm(protocols):
            root, ns = parse_tei(p, get_ns=True)
            divs = root.findall(f".//{ns['tei_ns']}div")
            empty = True
            if len(divs) > 1:
                for div in divs:
                    text = " ".join(div.itertext())
                    text = "".join(text.split())
                    if len(text) >= 1:
                        empty = False
                        continue

                if empty:
                    empty_count += 1
                    empty_protocols.append(p)
                    logger.error(f"Empty record (no text): {p}")
            else:
                empty_count += 1
                empty_protocols.append(p)
                logger.error(f"Record has no content divs: {p}")
        if empty_protocols:
            logger.debug(f"Empty records: {empty_protocols}")
        self.assertLessEqual(empty_count, CURRENT_NO_EMPTY_RECORDS, f"{empty_count} record(s) are empty or have no content divs")




if __name__ == '__main__':
    unittest.main()
