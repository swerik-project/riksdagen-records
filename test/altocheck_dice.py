"""
Check a sample of pages' text against corresponding alto files. Uses Dice coefficient + threshold to decide whether pages match or not.
Test fails if number of low-threshold documents increases in any year.
"""
from collections import Counter
from glob import glob
from lxml import etree
from nltk import edit_distance
from pathlib import Path
from pyriksdagen.io import parse_tei
from requests.adapters import HTTPAdapter
from trainerlog import get_logger
from tqdm import tqdm
from urllib3.util.retry import Retry
import alto
import json
import matplotlib.pyplot as plt
import os
import pandas as pd
import random
import requests
import unittest
import warnings




LOGGER = get_logger(Path(__file__).name)
session = requests.Session()                    # create session and retry if rate limited
retry = Retry(
    total=5,
    backoff_factor=1,
    status_forcelist=[429, 500, 502, 503, 504],
    allowed_methods=["GET"],
)
session.mount("https://", HTTPAdapter(max_retries=retry))
LOW_DICE_THRESHOLD = 0.6                        # We can tighten this up iteratively
CHECK_N_PAGES_PER_DECADE = 100                  #
RANDOM_SEED = 429                               # Ensure we test the same protocols / pages every time




def parse_clean_alto(content):
    """
    The alto module is picky
    """
    root = etree.fromstring(content)
    NS = {
        "alto": "http://www.loc.gov/standards/alto/ns-v3#"
    }
    allowed = {
        "{http://www.loc.gov/standards/alto/ns-v3#}ComposedBlock",
        "{http://www.loc.gov/standards/alto/ns-v3#}TextBlock",
    }

    for ps in root.xpath(".//alto:PrintSpace", namespaces=NS):
        for child in list(ps):
            if child.tag not in allowed:
                ps.remove(child)
    try:
        a = alto.Alto.from_xml(root)
    except Exception as e:
        print(type(e).__name__)
        print(repr(e))
    return a


def get_alto_words(alto_url, auth=None):
    """
    Get all words from tha alto file at the given url
    """
    r = session.get(alto_url, auth=auth, timeout=30)
    if r.content is None:
        warnings.warn("HTTP response has no content")
        return None#0, 0.0, 0
    try:
        altofile = parse_clean_alto(r.content) #alto.parse(r.content)
        words = altofile.extract_words()
    except:
        LOGGER.error("ALTO XML parsing unsuccessful")
        print("            ", r.status_code, r.headers.get("content-type"), alto_url)
        print("            ", r.content[:200])
        return None
    return words


def get_pc_words(root, page="random", ns="{http://www.tei-c.org/ns/1.0}"):
    """
    Get all words from random page on the fiven protocol
    """
    if page == "random":
        pbs = list(root.findall(f".//{ns}pb"))
        pb_sources = [pb.attrib["facs"] for pb in pbs]
        # TODO : remove next line once residual kblabb and data.riksdagen.se URLs are purged from the corpus
        pb_sources = [s for s in pb_sources if s.startswith("https://swerik-project.github.io/")]
        try:
            page_link = random.choice(pb_sources)
        except Exception as e:
            LOGGER.error("No FACS elements found")
            return None, None, None, None
        filename = page_link.split("/")[-1].split(".")[0]
        page = filename[-3:]
        LOGGER.info(f"Randomly selected page {page}")
        if not page.isdigit():
            LOGGER.warning(f"Page link does not end with a numeric index {page_link}")
    else:
        raise NotImplementedError("We haven't implemented anything other than selecting random pages.")
    words = []
    correct_page = False
    alto_url = None
    for body in root.findall(f".//{ns}body"):
        for div in root.findall(f".//{ns}div"):
            for elem in div:
                if elem.tag == f"{ns}pb":
                    correct_page = page_link == elem.attrib["facs"]
                    if correct_page:
                        pdf_url = elem.attrib["facs"]
                        alto_url = pdf_url.replace(
                                "https://swerik-project.github.io/riksdagen-records-pdf",
                                "https://raw.githubusercontent.com/swerik-project/riksdagen-records-alto/main/data"
                            ) + ".xml"
                        LOGGER.info(f"ALTO URL: {alto_url}")
                if correct_page:
                    clean_string = ' '.join([n.strip() for n in elem.itertext()]).strip()
                    words += clean_string.split()
    return words, alto_url, pdf_url, page


def dice_score(alto_words, tei_words):
    """
    Calculate dice score on the alto and tei words
    """
    alto = Counter(alto_words)
    tei = Counter(tei_words)
    overlap = sum((alto & tei).values())
    return 2 * overlap / (len(alto_words) + len(tei_words))


def calculate_dice(root, page="random"):
    """
    Prepare protocol page words and alto page words, then get a dice score.
    """
    words_pc, alto_url, pdf_url, page = get_pc_words(root, page=page)
    if words_pc is None:
        return None, None, None
    words_alto = get_alto_words(alto_url)
    if words_alto is None:
        return None, None, None#0, 0.0, 0
    return dice_score(words_alto, words_pc), alto_url, pdf_url


def plot_dice_boxplot(scores):
    """
    Box plot the dice scores from the test
    """
    plt.figure(figsize=(3, 6))
    plt.boxplot(scores, vert=True, showmeans=True)
    plt.ylabel("Dice score")
    plt.ylim(0, 1)
    plt.title(f"Dice scores (n={len(scores)})")
    plt.grid(axis="y", alpha=0.3)
    plt.savefig("test/results/alto-dice-boxplot.png")




class Test(unittest.TestCase):
    random.seed(RANDOM_SEED)

    def test_protocols(self):
        die = []
        die_rows = []
        die_cols = ["dice", "protocol", "alto", "pdf"]
        low_dice_by_year = {}
        lowest_die = 1
        lowest_die_prot = None
        no_facs_prots = []
        PAGES_PER_DECADE = CHECK_N_PAGES_PER_DECADE
        folder = "data/"
        #p = Path(folder)

        all_testcases = []
        decades = list(range(1860, 2021, 10))
        LOGGER.info(f"Testing decades: {decades}")
        LOGGER.info("-----------------------------------------")
        for decade in decades:
            testcases = list(glob(f"{folder}{decade // 10}*/*.xml"))
            testcases = sorted(testcases, key=lambda v: random.random())
            all_testcases = all_testcases + sorted(testcases[:PAGES_PER_DECADE])

        percentage_fail = []
        absolute_fail = []
        loading_fail = []
        for protocol_path in tqdm(all_testcases):
            year = protocol_path.split("/")[1]
            if year not in low_dice_by_year:
                low_dice_by_year[year] = 0
            LOGGER.info(f"Testing protocol {protocol_path}")
            protocol_id = protocol_path.split("/")[-1][:-4]
            root = parse_tei(protocol_path, get_ns=False)
            dice, alto_url, pdf_url = calculate_dice(root)
            if dice is None:
                no_facs_prots.append(protocol_path)
                continue
            die.append(dice)
            LOGGER.train(f"DICE :: {dice}")
            if dice < lowest_die:
                LOGGER.warning(f"{dice} is lowest, from {lowest_die}")
                lowest_die = dice
                lowest_die_prot = [protocol_path, alto_url, pdf_url]
            if dice < LOW_DICE_THRESHOLD:
                die_rows.append([dice, protocol_path, alto_url, pdf_url])
                low_dice_by_year[year] += 1
        with open("test/results/alto-low-dice-count-by-year.json", "w+") as jout:
            json.dump(low_dice_by_year, jout, indent=4, ensure_ascii=False)
        df = pd.DataFrame(die_rows, columns=die_cols)
        df.to_csv("test/results/alto-dice-low-score.tsv", sep='\t', index=False)
        plot_dice_boxplot(die)
        LOGGER.train("-----------------------------------------")
        LOGGER.train(f"min {min(die)} || max {max(die)}")
        LOGGER.info(f"Lowest die score {lowest_die}")
        [LOGGER.info(f"  >> {x}") for x in lowest_die_prot]
        LOGGER.info("------------")
        LOGGER.info(f"N w/ dice < 0.6 == {len(df)} || {len(df)/len(die)}")
        LOGGER.info("------------")
        LOGGER.info(f"N protocols without any FACS: {len(no_facs_prots)}")
        if os.path.exists("test/data/alto-low-dice-count-by-year.json"):
            with open("test/data/alto-low-dice-count-by-year.json", "r") as jin:
                thresholds = json.load(jin)
            test_passes = True
            for year, val in low_dice_by_year.items():
                if thresholds[year] < val:
                    LOGGER.error(f"Low Dice values have increased in {year}")
                    test_passes = False
                if thresholds[year] > val:
                    LOGGER.info(f"Threshold for {year} can be tightened to {val}")
            self.assertEqual(test_passes, True, f"Some years got worse. See logger errors directly above this failure.")
        else:
            LOGGER.warning(f"No low-Dice thresholds found. The test will pass, but nothing has been compared.")




if __name__ == '__main__':
    unittest.main()
