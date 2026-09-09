"""
Ensure records with unexpected URLs and records with no FACS don't increase.
"""
from glob import glob
from pathlib import Path
from pyriksdagen.io import parse_tei
from tqdm import tqdm
from trainerlog import get_logger
import json
import matplotlib.pyplot as plt
import os
import pandas as pd
import unittest




LOGGER = get_logger(Path(__file__).name)




class Test(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.records = sorted(glob("data/*/*.xml"))
        cls.N_url = 0
        cls.N_records = 0
        cls.bad_url = []
        cls.no_FACS_records = []
        cls.year_n_url = {}
        cls.year_bad_url = {}
        cls.year_n_record = {}
        cls.year_bad_record = {}


    @classmethod
    def tearDownClass(cls):
        def plot_problem_rate_by_year(totals,
                                      problems_df,
                                      title = None,
                                      filename = None
            ):
            # Number of problem cases per year
            problem_counts = problems_df["year"].value_counts().to_dict()

            years = sorted(totals.keys())
            percentages = [
                100 * problem_counts.get(year, 0) / totals[year]
                for year in years
            ]

            plt.figure(figsize=(10, 5))
            plt.plot(years, percentages)
             # Show decade labels only
            tick_pos = []
            tick_labels = []
            for y in years:
                first_year = int(str(y)[:4])   # 202223 -> 2022
                if first_year % 10 == 0:
                    tick_pos.append(y)
                    tick_labels.append(str(first_year))

            plt.xticks(tick_pos, tick_labels, rotation=90)
            plt.xlabel("Year")
            plt.ylabel("Problem cases (%)")
            plt.title(f"Percentage of {title} by year")
            plt.ylim(bottom=0)
            plt.grid(True, alpha=0.3)

            plt.savefig(f"test/results/{filename}.png")

        url_df = pd.DataFrame(cls.bad_url, columns=["record", "year", "FACS"])
        url_df.to_csv("test/results/unexpected-urls.tsv", sep='\t', index=False)
        facs_df = pd.DataFrame(cls.no_FACS_records, columns=["record", "year"])
        facs_df.to_csv("test/results/no-facs-records.tsv", sep='\t', index=False)
        with open("test/results/unexpected-urls.json", "w+") as utout:
            json.dump(cls.year_bad_url, utout, ensure_ascii=False, indent=4)
        with open("test/results/no-facs-records.json", "w+") as ftout:
            json.dump(cls.year_bad_record, ftout, ensure_ascii=False, indent=4)
        plot_problem_rate_by_year(cls.year_n_url,
                                  url_df,
                                  title = "unexpected URLs",
                                  filename="unexpected-urls")
        plot_problem_rate_by_year(cls.year_n_record,
                                  facs_df,
                                  title = "records with no FACS",
                                  filename = "no-facs-records")

        LOGGER.info("Test complete, generating summary:")
        LOGGER.info(f"Checked {cls.N_url} URLs")
        LOGGER.warning(f"Records with no FACS = {len(cls.no_FACS_records)}")
        LOGGER.warning(f"UNEXPECTED URL = {len(cls.bad_url)} ({len(cls.bad_url)/cls.N_url})")
        LOGGER.info("Done")


    def test_facs(self):
        for record in tqdm(self.records):
            year = record.split('/')[1]
            Test.N_records += 1
            if year not in Test.year_n_record:
                Test.year_n_record[year] = 0
            if year not in Test.year_bad_record:
                Test.year_bad_record[year] = 0
            Test.year_n_record[year] += 1
            root, ns = parse_tei(record)
            pbs = root.findall(f".//{ns['tei_ns']}pb")
            facs = [pb.attrib["facs"] for pb in pbs if "facs" in pb.attrib]

            if len(facs) == 0:
                Test.no_FACS_records.append([record, year])
                Test.year_bad_record[year] += 1
            for fac in facs:
                Test.N_url += 1
                if year not in Test.year_n_url:
                    Test.year_n_url[year] = 0
                if year not in Test.year_bad_url:
                    Test.year_bad_url[year] = 0
                Test.year_n_url[year] += 1
                if not fac.startswith("https://swerik-project.github.io"):
                    LOGGER.warning(f"Unexpected FACS value :: {fac}")
                    Test.bad_url.append([record, year, fac])
                    Test.year_bad_url[year] += 1

        if os.path.exists("test/data/unexpected-urls.json") and os.path.exists("test/data/no-facs-records.json"):
            test_passes = True
            with open("test/data/unexpected-urls.json", "r") as utin:
                url_thresholds = json.load(utin)
            with open("test/data/no-facs-records.json", "r") as ftin:
                nofacs_thresholds = json.load(ftin)
            for year, val in Test.year_bad_url.items():
                if url_thresholds[year] < val:
                    LOGGER.error(f"Unexpected urls increased in {year}")
                    test_passes = False
                if url_thresholds[year] > val:
                    LOGGER.info(f"Unexpected urls decreased in {year} to {val}; tighten threshold")
                if nofacs_thresholds[year] < Test.year_bad_record[year]:
                    LOGGER.error(f"Records with no FACS increased in {year}")
                    test_passes = False
                if nofacs_thresholds[year] > Test.year_bad_record[year]:
                    LOGGER.info(f"Records with no FACS decreased in {year} to {Test.year_bad_record[year]}")
                    LOGGER.info("tighten threshold")
            self.assertEqual(test_passes, True, "Unexpected URLs or records containing unexpexted URLs has increased. See logger messages directly above this.")
        else:
            LOGGER.warning("The test will pass, but there are no threshold files to compare years.")




if __name__ == '__main__':
    unittest.main()
