#!/usr/bin/env python3
from glob import glob
from matplotlib.ticker import PercentFormatter
from tqdm import tqdm
from trainerlog import get_logger
from pyriksdagen.io import parse_tei
import matplotlib.pyplot as plt
import os
import pandas as pd
import unittest




logger = get_logger(name="oneSpeaker")




class SingleSpeakerSpeech(unittest.TestCase):
    """
    Guarantee: each speech is attributed to a single speaker.
    """
    @classmethod
    def setUpClass(cls):
        cls.records = sorted(glob("data/*/*.xml"))
        cls.error_rows = []
        cls.speeches_per_year = {}


    @classmethod
    def tearDownClass(cls):

        def _plot_errors_by_year(df, totals):
            def start_year(value):
                return int(str(value)[:4])

            totals = pd.Series(totals)
            totals.index = totals.index.map(start_year)
            totals = totals.groupby(level=0).sum().sort_index()

            errors = (
                df["parliament_year"]
                .map(start_year)
                .value_counts()
                .reindex(totals.index, fill_value=0)
            )
            proportions = errors / totals.replace(0, float("nan"))

            fig, axes = plt.subplots(2, 1, sharex=True, figsize=(12, 7))

            axes[0].plot(errors.index, errors.values)
            axes[0].set_ylabel("Number of errors")

            axes[1].plot(proportions.index, proportions.values)
            axes[1].set_ylabel("Proportion of errors")
            axes[1].yaxis.set_major_formatter(PercentFormatter(xmax=1))
            axes[1].set_xlabel("Year (start of parliamentary sitting)")

            years = totals.index
            axes[1].set_xticks(
                range(((years.min() + 4) // 5) * 5, years.max() + 1, 5)
            )
            axes[1].tick_params(axis="x", labelrotation=90)

            for ax in axes:
                ax.grid(alpha=0.3)

            fig.tight_layout()
            return fig, axes

        if bool(os.environ.get("WRITE_UNITTEST_DIAGNOSTICS")):
            logger.info("Writing test diagnostics")
            cols = ["record", "parliament_year", "speech", "N_speakers"]
            df = pd.DataFrame(cls.error_rows, columns=cols)
            df.to_csv("test/results/multispeaker-speeches.tsv", index=False, sep="\t")
            f, a = _plot_errors_by_year(df, cls.speeches_per_year)
            plt.savefig(f"test/results/multispeaker-speeches.png")
        logger.info("Test is Finnish 🇫🇮")

    def test_speeches_have_one_speaker(self):
        """
        Guarantee: ensure speaker exclusivity in speeches extracted via the teiHeader / speech ID
        """
        def _get_speeches(root, ns):
            d = {}
            speeches = root.findall(f".//{ns['tei_ns']}constitution/{ns['tei_ns']}note[@type=\"speech\"]")
            for speech in speeches:
                Us = []
                id_ = speech.attrib[f"{ns['xml_ns']}id"]
                ptrs = speech.findall(f".//{ns['tei_ns']}ptr")
                for ptr in ptrs:
                    Us.append(ptr.attrib["target"][1:])
                d[id_] = Us
            return d

        def _count_whos(root, ns, Us):
            whos = set()
            for U in Us:
                u_elem = root.find(f".//{ns['tei_ns']}u[@{ns['xml_ns']}id=\"{U}\"]")
                who = u_elem.attrib[f"who"]
                if who != "unknown":
                    whos.add(who)
            return whos

        fail = False
        for record in tqdm(self.records[:]):
            py = record.split("/")[1]
            if py not in self.speeches_per_year:
                self.speeches_per_year[py] = 0
            root, ns = parse_tei(record)
            speeches = _get_speeches(root, ns)
            for speech, Us in speeches.items():
                self.speeches_per_year[py] += 1
                whos = _count_whos(root, ns, Us)
                if len(whos) > 1:
                    logger.warn(f"{record}:{speech} has {len(whos)} speakers assigned.")
                    self.error_rows.append([record, py, speech, len(whos)])
                    fail = True

        self.assertFalse(fail, "There are speeches with multiple assigned speakers.")




if __name__ == '__main__':
    unittest.main()
