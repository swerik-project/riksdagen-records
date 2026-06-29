#!/usr/bin/env python3
"""
Test protocols are in sequence.
"""
from datetime import datetime
from pyriksdagen.utils import (
    get_data_location,
    protocol_iterators,
)
from pytest_cfg_fetcher.fetch import fetch_config
from tqdm import tqdm
from trainerlog import get_logger
import pandas as pd
import os, unittest


logger = get_logger(name="records-in-sequence")


class Test(unittest.TestCase):

    def _add_ek_2_D(self, D, spl):
        year, sl1, N = spl[1], spl[2], spl[3]
        if sl1 == '':
            sl1 = '_'
        if N == '':
            N = 0
        if year not in D:
            D[year] = {}
        if sl1 not in D[year]:
            D[year][sl1] = []
        try:
            D[year][sl1].append(int(N))
        except:
            logger.error(f"Could not parse unicameral protocol number from filename parts: {spl}")
        return D

    def _add_tk_2_D(self, D, spl):
        year, sl1, chamber, sl2, N = spl[1], spl[2], spl[3], spl[4], spl[5]
        if sl1 == '':
            sl1 = '_'
        if sl2 == '':
            sl2 = '_'
        if year not in D:
            D[year] = {}
        if sl1 not in D[year]:
            D[year][sl1] = {}
        if chamber not in D[year][sl1]:
            D[year][sl1][chamber] = {}
        if sl2 not in D[year][sl1][chamber]:
            D[year][sl1][chamber][sl2] = []
        try:
            D[year][sl1][chamber][sl2].append(int(N))
        except:
            if N.endswith('a'):
                D[year][sl1][chamber][sl2].append(int(N[:-1]))
            else:
                D[year][sl1][chamber][sl2].append(5446)
        return D

    def _ck_duplicates(self, l):
        if len(l) == len(set(l)):
            return None
        else:
            u = []
            d = []
            for _ in l:
                if _ not in u:
                    u.append(_)
                else:
                    d.append(_)
            #print(f"WARNING! {len(d)} duplicate in range")
            return d

    def _ck_missing(self, l):
        l.sort()
        start, end = l[0], l[-1]
        #print(start, end, l)
        if start != 1:
            logger.warning(f"Protocol range starts at {start}, not 1")
            if start == 5446:
                print("... that's my number")
        missing = sorted(set(range(start, end + 1)).difference(l))
        if len(missing) > 0:
        #    print(f"WARNING! {len(missing)} missing from range")
            return start, end, missing
        else:
            return start, end, None

    def _iter_path(self, dict_in, prefix=None):
        if prefix is None:
            prefix = list()
        for key, value in dict_in.items():
            if not isinstance(value, dict):
                yield (prefix + [key], value)
            else:
                yield from self._iter_path(value, prefix + [key])

    def _iter_path_not_last(self, dict_in):
        for path in self._iter_path(dict_in, prefix=None):
            yield path


    def test_sequence(self):
        acceptable_exceptions = [
                ("1886", 40),
                ("1896", 25),
                ("1958", 17)
            ]
        dups = False
        miss = False
        lens = []
        D = {}
        protocols = sorted(list(protocol_iterators("data", start=1875, end=2022)))
        for prot in protocols:
            prot_base = os.path.basename(prot)[:-4]
            spl = prot_base.split('-')
            if len(spl) not in lens:
                lens.append(len(spl))
            if len(spl) == 4:
                D = self._add_ek_2_D(D, spl)
            if len(spl) >= 6:
                D = self._add_tk_2_D(D, spl)

        #print(lens)
        Dpaths = [p for p in self._iter_path_not_last(D)]

        rows = []
        cols = [
            "protocol_class", "N_protocols","range_first",
            "range_last", "N_duplicates", "N_missing",
            "duplicates", "missing"
        ]
        for _ in Dpaths:
            pc = '-'.join(_[0])
            logger.info(f"Checking protocol sequence for {pc}")
            duplicates = self._ck_duplicates(_[1])
            start, end, missing = self._ck_missing(_[1])
            if duplicates:
                N_dup = 0
                for d_d in duplicates:
                    if (_[0][0], d_d) not in acceptable_exceptions:
                        dups = True
                        N_dup += 1
                        logger.error(f"Duplicate protocol number in {pc}: {d_d}")
            else:
                N_dup = 0
            if missing:
                N_mis = len(missing)
                miss = True
                logger.error(f"{N_mis} protocol number(s) missing in {pc} range {start}-{end}")
                logger.debug(f"Missing protocol numbers for {pc}: {missing}")
            else:
                N_mis = 0
            rows.append([pc, len(_[1]), start, end, N_dup, N_mis, duplicates, missing])

        if duplicates == True or miss ==True:
            config = fetch_config("record-sequence")
            if config and config["test_sequence"]:
                now = datetime.now().strftime("%Y%m%d-%H%M%S")
                df = pd.DataFrame(rows, columns=cols)
                df.to_csv(
                    f"{config['test_out_dir']}/out-of-sequence_{now}.csv",
                    sep=";", index=False)
        self.assertFalse(dups, "Duplicate protocol numbers found outside accepted exceptions")
        self.assertFalse(miss, "Missing protocol numbers found in one or more protocol sequences")




if __name__ == '__main__':
    unittest.main()
