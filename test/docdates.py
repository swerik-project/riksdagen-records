"""
Sanity Check on docdates
"""
from datetime import datetime
from lxml import etree
from pyriksdagen.utils import (
    get_data_location,
    get_doc_dates,
    parse_tei,
    protocol_iterators,
)
from tqdm import tqdm
import pandas as pd
import unittest
import warnings


class Test(unittest.TestCase):

    def test_sane_docdates(self):
        protocols = sorted(list(protocol_iterators('data')))
        empty = 0
        last_end_date = None
        longer_than_a_week = []
        protocols_overlap = []
        protocols_overlap_cols = ["prot_a", "prot_b", "issue"]
        filename_date_mismatch = []
        fdm_cols = ["file", "issue"]
        date_format = "%Y-%m-%d"
        for i, p in enumerate(tqdm(protocols)):
            root, ns = parse_tei(p)
            me, p_docdates = get_doc_dates(p)
            p_docdates.sort()
            first = p_docdates[0]
            last = p_docdates[-1]
            if len(p_docdates) > 1:

                delta = datetime.strptime(last, date_format) - datetime.strptime(first, date_format)
                if delta.days > 7:
                    longer_than_a_week.append(p)

            if last_end_date:
                if last_end_date == first:
                    protocols_overlap.append([protocols[i-1], p, "share a day"])
                elif last_end_date > first:
                    protocols_overlap.append([protocols[i-1], p, "multiday overlap"])
            year = p.split('/')[1]
            if int(year) < 1875:
                mmdd = p.split('-')[-1][:-4]
                filenamedate = f"{year}-{mmdd[:2]}-{mmdd[-2:]}"
                if filenamedate not in p_docdates:
                    filename_date_mismatch.append([p, "filename date not in docdate"])
                else:
                    if len(set(p_docdates)) > 1:
                        filename_date_mismatch.append([p, "additional docdates than filename date"])

            last_end_date = last


        if len(longer_than_a_week) > 0:
            warnings.warn(f"FAIL:: {len(longer_than_a_week)} > 0...should be 0")
            with open("test/results/long-protocols.txt", "w+") as outf:
                [outf.write(f"{_}\n") for _ in longer_than_a_week]

        if len(protocols_overlap) > 0:
            warnings.warn(f"FAIL::: {len(protocols_overlap)} > 0...should be 0")
            df = pd.DataFrame(protocols_overlap, columns=protocols_overlap_cols)
            df.to_csv("test/results/protocols-overlap.csv", sep=';', index=False)

        if len(filename_date_mismatch) > 0:
            warnings.warn(f"FAIL::::: {len(filename_date_mismatch)} > 0...should be 0")
            df = pd.DataFrame(filename_date_mismatch, columns=fdm_cols)
            df.to_csv("test/results/filename-date-mismatch.csv", sep=';', index=False)

        assert len(longer_than_a_week) == 0
        assert len(protocols_overlap) == 0
        assert len(filename_date_mismatch) == 0

if __name__ == '__main__':
    # begin the unittest.main()
    unittest.main()
