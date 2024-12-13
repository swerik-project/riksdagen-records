#!/usr/bin/env python3
"""
Ensure there are no wonky things relating to doc dates.

.. include:: docs/dates-sanity-check.md
"""
from datetime import datetime
from glob import glob
from lxml import etree
from pyriksdagen.utils import (
    get_doc_dates,
    parse_tei,
    corpus_iterator,
)
from tqdm import tqdm
import os
import pandas as pd
import unittest
import warnings

class DatesSanityCheckTest(unittest.TestCase):
    """
    TestCase Class for running general sanity checks on doc dates. The following functions are defined
    """
    @classmethod
    def setUpClass(cls):
        """
        Set up common variables for these test cases.
        """
        super(DatesSanityCheckTest, cls).setUpClass()
        records = []
        dirs = sorted(os.listdir("data"))
        pys = [_ for _ in dirs if _ not in ["reg", "fort"] and os.path.isdir(f"data/{_}")]
        [records.extend(sorted(list(glob(f"data/{py}/*.xml")))) for py in pys]
        cls.records = records
        cls.N_records = len(records)
        cls.prerelease_nr = os.environ.get("RELEASE_NR", None)
        if cls.prerelease_nr is not None:
            df = pd.read_csv("test/results/dates-sanity-check.tsv", sep='\t')
            df.set_index("result", inplace=True)
            if cls.prerelease_nr not in df.columns:
                df[cls.prerelease_nr] = None
            cls.date_sanity_results = df


    @classmethod
    def tearDownClass(cls):
        """
        Write summary output when appropriate.
        """
        #print("\n\ntear down")
        #print(cls.__dict__.keys())
        if cls.prerelease_nr is not None:
            cls.date_sanity_results.at["total-N-records", cls.prerelease_nr] = cls.N_records
            cls.date_sanity_results.to_csv("test/results/dates-sanity-check.tsv", sep='\t')



    # until 1874 date matches filename
    def test_date_is_filename(self):
        """
        Check that doc dates from records up to 1874 match those in the file name.
        """
        rows = []
        cols = ["record", "offending_date", "other_date_ok"]
        c0, c1, c2 = 0, 0, 0
        for record in self.records:
            if int(record.split('/')[1]) <= 1874:
                c0 += 1
                err, dates = get_doc_dates(record)
                #print(record, dates)
                yyyy = record.split('/')[1]
                mm = record.split('-')[-1][:2]
                dd = record.split('-')[-1][2:4]
                reference_date = f"{yyyy}-{mm}-{dd}"
                correct_date_found = False
                incorrect_dates = []
                for date in dates:
                #    print("  ", date==reference_date, date, reference_date)
                    if date == reference_date:
                        correct_date_found = True
                    else:
                        incorrect_dates.append(date)
                if len(incorrect_dates) > 0:
                    c1 += 1
                    for incorrect_date in incorrect_dates:
                        c2 += 1
                        rows.append([record, incorrect_date, correct_date_found])
        print(c1, c2)
        if len(rows) > 0:
            df = pd.DataFrame(rows, columns=cols)
            print(len(df.loc[df["other_date_ok"] ==False, "record"].unique()))
        if self.prerelease_nr is not None:
            self.date_sanity_results.at["N-reords-1867-t-m-1874", self.prerelease_nr] = c0
            self.date_sanity_results.at["N-records-w-date-filename-mismatches-t-m-1874", self.prerelease_nr] = c1
            self.date_sanity_results.at["N-date-filename-mismatches-t-m-1874", self.prerelease_nr] = c2
            if df is not None:
                df.to_csv(f"test/results/dates-sanity-check/{self.prerelease_nr}_date-is-filename.csv", sep='\t', index=False)
        else:
            if df is not None:
                df.to_csv(f"test/results/dates-sanity-check/_date-is-filename.csv", sep='\t', index=False)

    # multiple dates span less than one week
    @unittest.skip
    def test_date_span_within_7_days(self):
        """
        Not implemented
        """
        pass


    # dates don't overlap from one protocol to the next
    def tests_no_overlap(self):
        """
        Check whether dates overlap, i.e. if one protocol starts on the same day or before the last doc date of the previous one.
        """
        last_prot = None
        last_prot_date = None
        c0, c1 = 0, 0
        rows = []
        cols = ["left_record", "lr_date[-1]", "rr_date[0]", "right_record"]
        for record in self.records:
            err, dates = get_doc_dates(record)
            if last_prot is not None:
                if dates[0] <= last_prot_date:
                    rows.append([last_prot, last_prot_date, dates[0], record])
                    #print(last_prot, last_prot_date, dates[0])
                    c0 += 1
                    if dates[0] != last_prot_date:
                        c1 += 1
            last_prot = record
            last_prot_date = dates[-1]
        print(c0, c1)
        if len(rows) > 0:
            df = pd.DataFrame(rows, columns=cols)
        if self.prerelease_nr is not None:
            self.date_sanity_results.at["N-date-overlaps+same-day", self.prerelease_nr] = c0
            self.date_sanity_results.at["N-date-overlaps-same-day", self.prerelease_nr] = c1
            if df is not None:
                df.to_csv(f"test/results/dates-sanity-check/{self.prerelease_nr}_dates-overlap.csv", sep='\t', index=False)
        else:
            if df is not None:
                df.to_csv(f"test/results/dates-sanity-check/_dates-overlap.csv", sep='\t', index=False)




if __name__ == '__main__':
    unittest.main()
