#!/usr/bin/env python3
"""
Quality estimation utilities for parliamentary protocol analyses.

This module provides the `QualityEstimator` class, which handles:
- Accuracy calculation per year
- Versioned CSV updates
- Plotting accuracy/coverage over multiple versions
"""
from functools import partial
import matplotlib.pyplot as plt
from multiprocessing import Pool
import os
import pandas as pd
from pyriksdagen.utils import infer_metadata
import re
from scipy.stats import beta
import sys
from tqdm import tqdm
from typing import(
    Callable, 
    List, 
    Optional
)

def version_number_is_valid(version):
    """
    Validate or set a default version string.
    Returns:
        str: Valid version string.
    """
    if not version:
        version = "v99.99.99"
    exp = re.compile(r"v\d+\.\d+\.\d+(?:b|rc\d+)?")
    if exp.fullmatch(version) or version == "v99.99.99":
        return version
    print(f"{version} is not a valid version number. Exiting.")
    sys.exit(1)

class QualityEstimator:
    """
    Generic class for estimating quality metrics (accuracy, coverage, etc.)
    per year across a set of parliamentary protocol records.

    Attributes:
        records (List[str]): List of protocol paths.
        estimate_path (str): Directory for CSVs and plots.
        version (str): Version string (default: 'v99.99.99').
        show (bool): Whether to show plots after generation.
        df_upper (pd.DataFrame): DataFrame of per-year metrics.
        df_difference (pd.DataFrame): Combined historical version data.
        fig (plt.Figure): Figure object for plotting.
        ax (plt.Axes): Axes object for plotting.
        pool (Pool): Multiprocessing pool for parallel computation.
    """

    def __init__(self, records: List[str], estimate_path: str, version: str = "v99.99.99", show: bool = False):
        self.records = records
        self.version = version
        self.show = show
        self.estimate_path = estimate_path
        self.gold_standard: Optional[pd.DataFrame] = None
        self.df_upper: Optional[pd.DataFrame] = None
        self.df_difference: Optional[pd.DataFrame] = None
        self.fig: Optional[plt.Figure] = None
        self.ax: Optional[plt.Axes] = None
        self.pool: Optional[Pool] = None


    def run(self, estimate_func: Callable, title: str = "Accuracy", column_list: List[str] = ["correct", "incorrect"], bounds: bool = True):
        """
        Run full estimation pipeline: calculate accuracy, update differences, and plot results.

        Args:
            estimate_func (Callable): Function that computes (year, correct, incorrect) per record.
            title (str): Plot title.
            column_list (List[str]): Column names for counts.
            bounds (bool): Whether to compute beta confidence intervals.
        """
        self.calculate_accuracy(estimate_func, column_list=column_list, bounds=bounds)

        self.df_upper.to_csv(os.path.join(self.estimate_path, "upper_bound.csv"), index=False)
        print(f"Upper bound {title} summary:")
        print(self.df_upper)
        print(f"Average {title}:", self.df_upper["accuracy"].mean())
        total_known = self.df_upper[column_list[0]].sum()
        total = self.df_upper[[column_list[0], column_list[1]]].sum().sum()
        print(f"Weighted average {title}:", total_known / total)
        min_idx = self.df_upper["accuracy"].idxmin()
        min_year = self.df_upper.loc[min_idx, "year"]
        min_value = self.df_upper.loc[min_idx, "accuracy"]
        print(f"Minimum {title}:", min_value, "at year:", min_year)

        self.update_difference()
        self.plot_versions(
            os.path.join(self.estimate_path, f"{title.replace(' ', '-')}.png"),
            n_versions=6,
            title=title
        )
        self.teardown()

    def teardown(self):
        """Close figures and terminate multiprocessing pool."""
        if self.fig is not None:
            plt.close(self.fig)
            self.fig = None
            self.ax = None
        if self.pool is not None:
            self.pool.close()
            self.pool.join()
            self.pool = None
        self.df_upper = None
        self.df_difference = None
        print("Resources cleaned up.")

    @staticmethod
    def pathize_protocol_id(protocol_id: str) -> str:
        """
        Convert a protocol ID to a data path.

        Args:
            protocol_id (str): Protocol identifier.

        Returns:
            str: File path.

        Raises:
            FileNotFoundError: If no valid path exists.
        """
        spl = protocol_id.split('-')
        py = spl[1]
        suffix = ""
        if len(spl) == 4:
            nr = spl[3]
            pren = '-'.join(spl[:3])
        else:
            nr = spl[5]
            pren = '-'.join(spl[:5])
            if len(spl) == 7:
                suffix = f"-{spl[-1]}"
        path_ = f"data/{py}/{pren}-{nr:0>3}{suffix}.xml"
        if os.path.exists(path_):
            return path_
        path_ = re.sub(r'((extra)?h[^-]+st|")', '', path_)
        if os.path.exists(path_):
            return path_
        raise FileNotFoundError(f"Can't find {path_}")
    
    @staticmethod
    def version_key(v: str) -> List[int]:
        """Sort key for semantic versioning."""
        if v == "v99.99.99":
            return [999, 999, 999]
        if not v.startswith("v"):
            v = "v" + v
        parts = v[1:].split(".")
        if len(parts) != 3:
            raise ValueError(f"Invalid version string: {v!r} (must be 'vX.Y.Z')")
        try:
            return [int(p) for p in parts]
        except ValueError:
            raise ValueError(f"Invalid version string: {v!r} (non-integer component)")


    class _Worker:
        """Callable wrapper so workers only need the record."""
        def __init__(self, estimate_func, gold_standard):
            self.estimate_func = estimate_func
            self.gold_standard = gold_standard

        def __call__(self, rec):
            return self.estimate_func(rec, self.gold_standard)


    def calculate_accuracy(self, estimate_func: Callable, column_list: List[str] = ["correct", "incorrect"], bounds: bool = True) -> pd.DataFrame:
        """
        Compute per-year counts and accuracy.
        """
        years = sorted({int(str(infer_metadata(p).get("year"))[:4]) for p in self.records})
        df_upper = pd.DataFrame(0, index=years, columns=[column_list[0], column_list[1]])

        worker = QualityEstimator._Worker(estimate_func, self.gold_standard)

        self.pool = Pool()
        for year, val1, val2 in tqdm(
            self.pool.imap_unordered(worker, self.records),
            total=len(self.records)
        ):
            if year in df_upper.index:
                df_upper.loc[year, column_list[0]] += val1
                df_upper.loc[year, column_list[1]] += val2

        df_upper['accuracy'] = df_upper[column_list[0]] / df_upper.sum(axis=1)

        if bounds:
            df_upper['lower'] = df_upper.apply(
                lambda r: beta.ppf(0.05, r[column_list[0]]+1, r[column_list[1]]+1), axis=1
            )
            df_upper['upper'] = df_upper.apply(
                lambda r: beta.ppf(0.95, r[column_list[0]]+1, r[column_list[1]]+1), axis=1
            )

        df_upper = df_upper.reset_index().rename(columns={'index': 'year'})
        df_upper.insert(0, 'version', self.version)
        self.df_upper = df_upper
        return df_upper

    def update_difference(self) -> pd.DataFrame:
        """
        Update or create a CSV combining all versions.

        Returns:
            pd.DataFrame: Combined historical data.
        """
        diff_path = os.path.join(self.estimate_path, "difference.csv")
        byyear = self.df_upper.copy()
        byyear["version"] = self.version

        if os.path.exists(diff_path):
            existing = pd.read_csv(diff_path)
            if self.version == "v99.99.99":
                existing = existing[existing["version"] != "v99.99.99"]
                combined = pd.concat([existing, byyear], ignore_index=True)
            else:
                if self.version in existing["version"].unique():
                    print(f"Version {self.version} already exists in {diff_path}, skipping append.")
                    combined = existing
                else:
                    combined = pd.concat([existing, byyear], ignore_index=True)
        else:
            combined = byyear

        combined.to_csv(diff_path, index=False)
        self.df_difference = combined
        return combined

    def plot_versions(self, output_path: str, ax: Optional[plt.Axes] = None, n_versions: int = 6, title: str = "Accuracy per Year", y_label: str = "Accuracy"):
        """
        Plot accuracy/coverage per version.

        Args:
            output_path (str): Where to save the figure.
            ax (plt.Axes, optional): Existing axes to plot on.
            n_versions (int): Number of latest versions to show.
            title (str): Plot title.
            y_label (str): Y-axis label.
        """
        df = self.df_difference.copy()
        df["version"] = df["version"].astype(str).str.strip()

        if ax is None:
            self.fig, self.ax = plt.subplots(figsize=(12, 6))
        else:
            self.ax = ax
            self.fig = ax.figure

        valid_versions = [v for v in df["version"].unique() if "rc" not in str(v).lower()]
        version_sorted = sorted(valid_versions, key=self.version_key, reverse=True)[:n_versions]

        colors = list("bgrcmyk")
        for i, v in enumerate(version_sorted):
            dfv = df[df["version"] == v].copy()
            if dfv.empty:
                continue
            dfv = dfv.sort_values("year")
            self.ax.plot(dfv["year"], dfv["accuracy"], linewidth=1.75, label=v, color=colors[i % len(colors)])

        self.ax.set_title(title)
        self.ax.set_xlabel("Beginning of parliamentary year")
        self.ax.set_ylabel(y_label)
        self.ax.legend(loc="upper left")
        self.fig.tight_layout()
        self.fig.savefig(output_path)

        if self.show and self.fig is not None:
            self.fig.show()