#!/usr/bin/env python3
from glob import glob
from matplotlib.ticker import PercentFormatter
from tqdm import tqdm
from trainerlog import get_logger
from pyriksdagen.io import parse_tei
import matplotlib.pyplot as plt
import os
import polars as pl
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
            # Handles both 1867 and sitting identifiers such as 198081.
            year_expr = (
                pl.col("parliament_year")
                .cast(pl.String)
                .str.slice(0, 4)
                .cast(pl.Int64)
            )

            totals_df = (
                pl.DataFrame({
                    "parliament_year": [str(year) for year in totals],
                    "total": list(totals.values()),
                })
                .with_columns(year_expr)
                .group_by("parliament_year")
                .agg(pl.col("total").sum())
            )

            errors_df = (
                df.with_columns(year_expr)
                .group_by("parliament_year")
                .agg(pl.len().alias("errors"))
            )

            plot_df = (
                totals_df
                .join(errors_df, on="parliament_year", how="left")
                .with_columns(pl.col("errors").fill_null(0))
                .with_columns(
                    pl.when(pl.col("total") != 0)
                    .then(pl.col("errors") / pl.col("total"))
                    .otherwise(float("nan"))
                    .alias("proportion")
                )
                .sort("parliament_year")
            )

            years = plot_df["parliament_year"].to_numpy()

            fig, axes = plt.subplots(2, 1, sharex=True, figsize=(12, 7))

            axes[0].plot(years, plot_df["errors"].to_numpy())
            axes[0].set_ylabel("Number of errors")

            axes[1].plot(years, plot_df["proportion"].to_numpy())
            axes[1].set_ylabel("Proportion of errors")
            axes[1].yaxis.set_major_formatter(PercentFormatter(xmax=1))
            axes[1].set_xlabel("Year (start of parliamentary sitting)")

            axes[1].set_xticks(
                range(((int(years.min()) + 4) // 5) * 5, int(years.max()) + 1, 5)
            )
            axes[1].tick_params(axis="x", labelrotation=90)

            for ax in axes:
                ax.grid(alpha=0.3)

            fig.tight_layout()
            return fig, axes

        if bool(os.environ.get("WRITE_UNITTEST_DIAGNOSTICS")):
            logger.info("Writing test diagnostics")
            cols = ["record", "parliament_year", "speech", "N_speakers"]

            df = pl.DataFrame(cls.error_rows, schema=cols, orient="row")
            df.write_csv("test/results/multispeaker-speeches.tsv",
                        separator="\t")
            fig, ax = _plot_errors_by_year(df, cls.speeches_per_year)
            plt.savefig("test/results/multispeaker-speeches.png")
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
