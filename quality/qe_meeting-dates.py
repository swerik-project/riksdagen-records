#!/usr/bin/env python3
"""
Validate protocol dates against a gold-standard CSV and generate metrics.

Setup/teardown ensures resources (figures, pools) are cleaned up after each run.
"""
import argparse
import matplotlib.pyplot as plt
from multiprocessing import Pool
import os
import pandas as pd
from pyriksdagen.io import parse_tei
from pyriksdagen.utils import get_doc_dates
import sys
from typing import (
    Dict,
    List,
    Tuple,
    Union
)

class ProtocolValidationRunner:
    def __init__(self, annotated_data=None, estimate_path="quality/estimates/record_dates", num_processes=4, show=False):

        self.annotated_data = annotated_data
        self.estimate_path = estimate_path
        self.num_processes = num_processes
        self.show = show

        self.df = None
        self.missing_in_xml_all = []
        self.extra_in_xml_all = []
        self.fig = None
        self.pool = None

    def setup(self):
        """Prepare directories and read input CSV(s)."""
        if isinstance(self.annotated_data, str):
            self.annotated_data = [self.annotated_data]

        dfs = []
        for path in self.annotated_data:
            if not os.path.exists(path):
                sys.exit(f"CSV not found: {path}")
            print(f"Reading: {path}")
            df = pd.read_csv(path)

            if 'pdf_url' not in df.columns or 'docDate' not in df.columns:
                sys.exit(f"CSV {path} must contain 'pdf_url' and 'docDate' columns")

            dfs.append(df)

        self.df = pd.concat(dfs, ignore_index=True)

        os.makedirs(self.estimate_path, exist_ok=True)

    def teardown(self):
        """Clean up resources like plots and pools."""
        if self.fig is not None:
            plt.close(self.fig)
            self.fig = None
        if self.pool is not None:
            self.pool.close()
            self.pool.join()
            self.pool = None
        print("Resources cleaned up.")

def extract_relative_path(pdf_url):
    """
    Convert a PDF URL to the corresponding XML relative path.
    """
    prefix = "https://pdf.swedeb.se/riksdagen-records-pdf/"
    if pdf_url.startswith(prefix):

        relative_path = pdf_url[len(prefix):]

        if relative_path.endswith(".pdf"):
            relative_path = relative_path[:-4]

        return f"data/{relative_path}.xml"
    else:
        print(f"Warning: PDF URL does not match expected prefix: {pdf_url}")
        return pdf_url

def process_protocol(args):
    """
    Compare gold-standard dates with XML-extracted dates for a single protocol.
    
    Returns:
        tuple:
            missing_in_xml (list[dict]): List of gold-standard dates missing in XML.
            extra_in_xml (list[dict]): List of XML dates not present in gold-standard.
    """
    protocol_path, rows = args
    if not os.path.exists(protocol_path):
        return [], [{'file_path': protocol_path, 'gold_standard_date': ';'.join(map(str, rows['docDate'].dropna())), 'xml_dates': 'FILE_NOT_FOUND'}]
    try:
        root, ns = parse_tei(protocol_path)
        _, xml_dates = get_doc_dates(root)
    except Exception as e:
        return [], [{'file_path': protocol_path, 'gold_standard_date': ';'.join(map(str, rows['docDate'].dropna())), 'xml_dates': f'ERROR: {str(e)}'}]
    gold_dates = set(rows['docDate'].dropna())
    xml_dates_set = set(xml_dates)
    missing_in_xml = [{'file_path': protocol_path, 'gold_standard_date': d, 'xml_dates': ';'.join(str(x) for x in xml_dates)} for d in (gold_dates - xml_dates_set)]
    extra_in_xml = [{'file_path': protocol_path, 'gold_standard_date': ';'.join(str(d) for d in gold_dates), 'xml_dates': d} for d in (xml_dates_set - gold_dates)]
    return missing_in_xml, extra_in_xml

def calculate_metrics(missing, extra, df):
    """
    Compute precision, recall, and F1-score per year and overall.

    Returns:
        metrics_per_year (dict): Yearly metrics with keys 'gold', 'fp', 'fn', 'precision', 'recall', 'f1'.
        overall_metrics (dict): Overall precision, recall, and F1-score across all years.
    """
    metrics_per_year = {}
    for _, row in df.iterrows():
        path = row['pdf_url']
        year = int(path.split('/')[1][:4])
        if year not in metrics_per_year:
            metrics_per_year[year] = {'gold': 0, 'fp': 0, 'fn': 0}
        metrics_per_year[year]['gold'] += 1
    for m in missing:
        year = int(m['file_path'].split('/')[1][:4])
        metrics_per_year[year]['fn'] += 1
    for e in extra:
        year = int(e['file_path'].split('/')[1][:4])
        metrics_per_year[year]['fp'] += 1
    for year, stats in metrics_per_year.items():
        tp = max(0, stats['gold'] - stats['fn'])
        precision = tp / (tp + stats['fp']) if (tp + stats['fp']) > 0 else 0
        recall = tp / (tp + stats['fn']) if (tp + stats['fn']) > 0 else 0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0
        stats.update({'precision': precision, 'recall': recall, 'f1': f1})
    total_tp = sum(max(0, stats['gold'] - stats['fn']) for stats in metrics_per_year.values())
    total_fp = sum(stats['fp'] for stats in metrics_per_year.values())
    total_fn = sum(stats['fn'] for stats in metrics_per_year.values())
    overall_metrics = {
        'precision': total_tp / (total_tp + total_fp) if (total_tp + total_fp) > 0 else 0,
        'recall': total_tp / (total_tp + total_fn) if (total_tp + total_fn) > 0 else 0
    }
    overall_metrics['f1'] = 2 * overall_metrics['precision'] * overall_metrics['recall'] / (
        overall_metrics['precision'] + overall_metrics['recall']) if (overall_metrics['precision'] + overall_metrics['recall']) > 0 else 0
    return metrics_per_year, overall_metrics

def plot_metrics(metrics_file, output_dir, show = False):
    """
    Generate plots of precision, recall, and F1-score per year for all available versions.

    Args:
        metrics_file (str): CSV file containing columns ['year', 'precision', 'recall', 'f1', 'version'].
        output_dir (str): Directory to save generated plots.
        show (bool, default=False): Whether to display plots interactively.
    """
    if not os.path.exists(metrics_file):
        print(f"Metrics file {metrics_file} not found. Cannot plot.")
        return

    df = pd.read_csv(metrics_file)

    if "version" not in df.columns:
        df["version"] = "v99.99.99"

    metrics = ["precision", "recall", "f1"]
    os.makedirs(output_dir, exist_ok=True)

    for metric in metrics:
        fig, ax = plt.subplots(figsize=(10, 6))
        for version, group in df.groupby("version"):
            group = group.sort_values("year")
            ax.plot(group["year"], group[metric], label=version)
        ax.set_xlabel("Year")
        ax.set_ylabel(metric.capitalize())
        ax.set_title(f"{metric.capitalize()} by Year (per Version)")
        ax.set_ylim(0, 1.05)
        ax.grid(True)
        ax.legend(title="Version")
        plt.tight_layout()

        output_file = os.path.join(output_dir, f"{metric}_by_year.png")
        fig.savefig(output_file)
        print(f"Plot saved to {output_file}")
        if show:
            plt.show()
        plt.close(fig)

def main(args):
    runner = ProtocolValidationRunner(
        annotated_data=args.annotated_data,
        estimate_path=args.estimate_path,
        num_processes=args.num_processes,
        show=args.show
    )

    runner.setup()
    df = runner.df
    df['pdf_url'] = df['pdf_url'].apply(extract_relative_path)
    grouped = [(protocol, group) for protocol, group in df.groupby('pdf_url')]
    runner.pool = Pool(processes=runner.num_processes)
    results = runner.pool.map(process_protocol, grouped)
    runner.pool.close()
    runner.pool.join()
    runner.pool = None
    runner.missing_in_xml_all = [item for sublist in results for item in sublist[0]]
    runner.extra_in_xml_all = [item for sublist in results for item in sublist[1]]

    if runner.missing_in_xml_all:
        pd.DataFrame(runner.missing_in_xml_all).to_csv(
            os.path.join(runner.estimate_path, "missing_annotations_fn.csv"), index=False)
    if runner.extra_in_xml_all:
        pd.DataFrame(runner.extra_in_xml_all).to_csv(
            os.path.join(runner.estimate_path, "wrong_annotations_fp.csv"), index=False)

    metrics_per_year, overall_metrics = calculate_metrics(
        runner.missing_in_xml_all, runner.extra_in_xml_all, df)
    
    print("Overall metrics:")
    print(f"Precision: {overall_metrics['precision']:.2%}")
    print(f"Recall:    {overall_metrics['recall']:.2%}")
    print(f"F1-score:  {overall_metrics['f1']:.2%}")

    metrics_file = os.path.join(runner.estimate_path, "date_metrics.csv")

    new_metrics_df = pd.DataFrame([{'year': y, **stats} for y, stats in metrics_per_year.items()])

    version = getattr(args, "version", "v99.99.99")
    new_metrics_df["version"] = version

    if os.path.exists(metrics_file):
        existing = pd.read_csv(metrics_file)
        if "version" not in existing.columns:
            existing["version"] = "v99.99.99"
            print("Info: version column missing in existing metrics, assigning default v99.99.99")


        if version in existing["version"].unique():
            if version == "v99.99.99":
                existing = existing[existing["version"] != "v99.99.99"]
                updated = pd.concat([existing, new_metrics_df], ignore_index=True)
                print(f"Overwriting standard version {version} in {metrics_file}")
            else:
                sys.exit(f"Version {version} already exists in {metrics_file}. Aborting.")
        else:
            updated = pd.concat([existing, new_metrics_df], ignore_index=True)
            print(f"Appended new version {version} to {metrics_file}")
    else:
        updated = new_metrics_df
        print(f"Created new metrics file with version {version}")

    updated = updated[['version'] + [c for c in updated.columns if c != 'version']]
    updated.to_csv(metrics_file, index=False)

    plot_metrics(metrics_file, runner.estimate_path, show=runner.show)
    runner.teardown()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Validate protocol dates against gold-standard CSV')
    parser.add_argument(
        "-d", "--annotated-data",
        default = ["quality/data/record-dates/goldstandard-dates-expert.csv","quality/data/record-dates/goldstandard-dates-student.csv"],
        type=str,
        nargs="*",
        help="CSV(s) with gold-standard dates. If none given, two defaults are used."
    )
    parser.add_argument(
        "-o", "--estimate-path",
        type=str,
        default="quality/estimates/record_dates",
        help="Directory to save results (default: %(default)s)"
    )
    parser.add_argument("--show", action="store_true", help="Show plots interactively")
    parser.add_argument("--num_processes", type=int, default=4, help="Number of parallel processes")
    parser.add_argument("--version", type=str, default="v99.99.99", help="Version tag for this run (default: v99.99.99)")
    args = parser.parse_args()

    main(args)
