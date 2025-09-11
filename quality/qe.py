#!/usr/bin/env python3
"""
Quality estimation utilities for parliamentary protocol analyses.

This module provides the `QualityEstimator` class, which handles:
- Accuracy calculation per year
- Versioned CSV updates
- Plotting accuracy/coverage over multiple versions
"""

import os
import re
import sys
import pandas as pd
import matplotlib.pyplot as plt
from scipy.stats import beta
from tqdm import tqdm
from pyriksdagen.utils import infer_metadata
from multiprocessing import Pool
from typing import Callable, List, Optional


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
        self.df_upper: Optional[pd.DataFrame] = None
        self.df_difference: Optional[pd.DataFrame] = None
        self.fig: Optional[plt.Figure] = None
        self.ax: Optional[plt.Axes] = None
        self.pool: Optional[Pool] = None

    # ------------------------
    # Full pipeline
    # ------------------------
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
        self.update_difference()
        self.plot_versions(
            os.path.join(self.estimate_path, f"{title.replace(' ', '-')}.png"),
            n_versions=6,
            title=title
        )

        if self.show and self.fig is not None:
            self.fig.show()

    # ------------------------
    # Cleanup
    # ------------------------
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

    def __del__(self):
        self.teardown()

    # ------------------------
    # Version validation
    # ------------------------
    def validate_version(self) -> str:
        """
        Validate or set a default version string.

        Returns:
            str: Valid version string.
        """
        if not self.version:
            self.version = "v99.99.99"
        exp = re.compile(r"v\d+\.\d+\.\d+(?:b|rc\d+)?")
        if exp.fullmatch(self.version) or self.version == "v99.99.99":
            return self.version
        print(f"{self.version} is not a valid version number. Exiting.")
        sys.exit(1)

    # ------------------------
    # Protocol ID to path
    # ------------------------
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

    # ------------------------
    # Version sorting
    # ------------------------
    @staticmethod
    def version_key(v: str) -> List[int]:
        """Sort key for semantic versioning."""
        if v == "v99.99.99":
            return [999, 999, 999]
        try:
            return list(map(int, v[1:].split(".")))
        except Exception:
            return [0, 0, 0]

    # ------------------------
    # Accuracy calculation
    # ------------------------
    def calculate_accuracy(self, estimate_func: Callable, column_list: List[str] = ["correct", "incorrect"], bounds: bool = True) -> pd.DataFrame:
        """
        Compute per-year counts and accuracy.

        Args:
            estimate_func (Callable): Function returning (year, count1, count2) per record.
            column_list (List[str]): Names for the two count columns.
            bounds (bool): Compute beta confidence intervals if True.

        Returns:
            pd.DataFrame: Per-year metrics.
        """
        years = sorted({int(str(infer_metadata(p).get("year"))[:4]) for p in self.records})
        df_upper = pd.DataFrame(0, index=years, columns=[column_list[0], column_list[1]])

        self.pool = Pool()
        for year, val1, val2 in tqdm(self.pool.imap(estimate_func, self.records), total=len(self.records)):
            if year in df_upper.index:
                df_upper.loc[year, column_list[0]] += val1
                df_upper.loc[year, column_list[1]] += val2

        df_upper['accuracy'] = df_upper[column_list[0]] / df_upper.sum(axis=1)

        if bounds:
            df_upper['lower'] = df_upper.apply(lambda r: beta.ppf(0.05, r[column_list[0]]+1, r[column_list[1]]+1), axis=1)
            df_upper['upper'] = df_upper.apply(lambda r: beta.ppf(0.95, r[column_list[0]]+1, r[column_list[1]]+1), axis=1)

        df_upper = df_upper.reset_index().rename(columns={'index': 'year'})
        df_upper.insert(0, 'version', self.version)
        self.df_upper = df_upper
        return df_upper

    # ------------------------
    # Difference CSV
    # ------------------------
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

    # ------------------------
    # Plot versions
    # ------------------------
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