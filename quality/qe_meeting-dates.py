#!/usr/bin/env python3
"""
Validate protocol dates against a gold-standard CSV and generate both
record-level and protocol-level metrics. Results are stored in separate
folders with plots and subtables per year.

Setup/teardown ensures resources (figures, pools) are cleaned up after each run.
"""
import argparse
import matplotlib.pyplot as plt
from multiprocessing import Pool
import numpy as np
import os
import pandas as pd
from pyriksdagen.io import parse_tei
from pyriksdagen.utils import get_doc_dates, infer_metadata
import re
import warnings

def version_key(v):
    nums = re.findall(r'\d+', v)
    return tuple(map(int, nums))

def join_dates(dates):
    return ';'.join(str(d) for d in dates)


def safe_f1(precision, recall):
    return 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0


def extract_relative_path(pdf_url):
    """Convert full PDF URL to corresponding XML file path."""
    prefix = "https://pdf.swedeb.se/riksdagen-records-pdf/"
    if pdf_url.startswith(prefix):
        relative_path = pdf_url[len(prefix):]
        if relative_path.endswith(".pdf"):
            relative_path = relative_path[:-4]
        return f"data/{relative_path}.xml"
    else:
        warnings.warn(
            f"PDF URL does not match expected prefix: {pdf_url}",
            category=UserWarning
        )
        return pdf_url

class ProtocolValidationRunner:
    """Handles setup, teardown, and shared state for protocol validation."""
    def __init__(self, annotated_data=None, estimate_path="quality/estimates", show=False, use_pool=False, num_processes=4):
        self.annotated_data = annotated_data
        self.estimate_path = estimate_path
        self.show = show
        self.pool = Pool(processes=num_processes) if use_pool else None

        self.df = None
        self.missing_in_xml_all = []
        self.extra_in_xml_all = []
        self.protocol_level_results = []

    def setup(self):
        """Read and validate gold-standard CSV files."""
        if isinstance(self.annotated_data, str):
            self.annotated_data = [self.annotated_data]

        dfs = []
        for path in self.annotated_data:
            if not os.path.exists(path):
                raise FileNotFoundError(f"CSV not found: {path}")

            print(f"Reading: {path}")
            df = pd.read_csv(path)

            if 'pdf_url' not in df.columns or 'docDate' not in df.columns:
                raise ValueError(
                    f"CSV {path} must contain 'pdf_url' and 'docDate' columns"
                )

            dfs.append(df)

        self.df = pd.concat(dfs, ignore_index=True)


    def teardown(self):
        """Close pool to free resources."""
        if self.pool is not None:
            self.pool.close()
            self.pool.join()
            self.pool = None

        plt.close('all')
        print("Resources cleaned up.")



def process_protocol(args):
    """Process a single protocol and return missing and extra date records."""
    protocol_path, rows = args
    gold_dates = set(rows['docDate'].dropna())

    if not os.path.exists(protocol_path):
        return [], [{'file_path': protocol_path, 'gold_standard_date': join_dates(gold_dates),
                     'xml_dates': 'FILE_NOT_FOUND'}], (protocol_path, gold_dates, set())

    try:
        root, ns = parse_tei(protocol_path)
        _, xml_dates = get_doc_dates(root)
    except Exception as e:
        return [], [{'file_path': protocol_path, 'gold_standard_date': join_dates(gold_dates),
                     'xml_dates': f'ERROR: {str(e)}'}], (protocol_path, gold_dates, set())

    xml_dates_set = set(xml_dates)
    missing_in_xml = [{'file_path': protocol_path, 'gold_standard_date': d,
                       'xml_dates': join_dates(xml_dates)} for d in (gold_dates - xml_dates_set)]
    extra_in_xml = [{'file_path': protocol_path, 'gold_standard_date': join_dates(gold_dates),
                     'xml_dates': d} for d in (xml_dates_set - gold_dates)]

    return missing_in_xml, extra_in_xml, (protocol_path, gold_dates, xml_dates_set)


def calculate_record_level_metrics(missing, extra, df):
    """Compute record-level metrics per year and overall."""
    metrics_per_year = {}

    for path in df['pdf_url']:
        year = infer_metadata(path)["year"]
        metrics_per_year.setdefault(year, {'gold': 0, 'fp': 0, 'fn': 0})
        metrics_per_year[year]['gold'] += 1

    for m in missing:
        year = infer_metadata(m['file_path'])["year"]
        metrics_per_year[year]['fn'] += 1
    for e in extra:
        year = infer_metadata(e['file_path'])["year"]
        metrics_per_year[year]['fp'] += 1

    for stats in metrics_per_year.values():
        tp = max(0, stats['gold'] - stats['fn'])
        stats['precision'] = tp / (tp + stats['fp']) if (tp + stats['fp']) > 0 else 0
        stats['recall'] = tp / (tp + stats['fn']) if (tp + stats['fn']) > 0 else 0
        stats['f1'] = safe_f1(stats['precision'], stats['recall'])
        stats['jaccard'] = tp / (tp + stats['fp'] + stats['fn']) if (tp + stats['fp'] + stats['fn']) > 0 else 0

    total_tp = sum(max(0, stats['gold'] - stats['fn']) for stats in metrics_per_year.values())
    total_fp = sum(stats['fp'] for stats in metrics_per_year.values())
    total_fn = sum(stats['fn'] for stats in metrics_per_year.values())
    precision = total_tp / (total_tp + total_fp) if (total_tp + total_fp) > 0 else 0
    recall = total_tp / (total_tp + total_fn) if (total_tp + total_fn) > 0 else 0
    overall_metrics = {'precision': precision, 'recall': recall, 'f1': safe_f1(precision, recall)}

    return metrics_per_year, overall_metrics


def calculate_protocol_level_metrics(protocol_results):
    """Compute protocol-level metrics: Jaccard, avg Jaccard, accuracy (J=1), and coverage (D ⊆ hat D)."""
    records = []

    for doc_path, gold_set, pred_set in protocol_results:
        union_len = len(gold_set | pred_set)
        jaccard = len(gold_set & pred_set) / union_len if union_len > 0 else 1.0
        accuracy = int(jaccard == 1)
        coverage = int(gold_set <= pred_set)
        year = infer_metadata(doc_path)["year"]

        records.append({
            'year': year,
            'jaccard': jaccard,
            'accuracy': accuracy,
            'coverage': coverage
        })

    df = pd.DataFrame(records)

    per_year_metrics = df.groupby('year')[['jaccard', 'accuracy', 'coverage']].mean().rename(
        columns={'jaccard': 'avg_jaccard'}
    ).to_dict(orient='index')

    overall_metrics = {
        'avg_jaccard': float(df['jaccard'].mean()),
        'accuracy': float(df['accuracy'].mean()),
        'coverage': float(df['coverage'].mean())
    }

    return per_year_metrics, overall_metrics


def plot_metrics(metrics_file, output_dir, metric_type="Metric", show=False):
    """Plot yearly metrics for each version."""
    if not os.path.exists(metrics_file):
        print(f"Metrics file {metrics_file} not found. Cannot plot.")
        return

    df = pd.read_csv(metrics_file)
    df["version"] = df.get("version", "v99.99.99")
    metrics = [c for c in df.columns if c not in ['year', 'version', 'gold', 'fp', 'fn']]
    os.makedirs(output_dir, exist_ok=True)

    for metric in metrics:
        fig, ax = plt.subplots(figsize=(10, 6))
        for v in sorted(df["version"].unique(), key=version_key, reverse=True):
            group = df[df["version"] == v].sort_values("year")
            ax.plot(group["year"], group[metric], label=v)
        ax.set_xlabel("Year")
        ax.set_ylabel(metric.capitalize())
        ax.set_title(f"{metric_type} {metric.capitalize()} by Year (per Version)")
        ax.set_ylim(0, 1.05)
        ax.grid(True)
        ax.legend(title="Version")
        plt.tight_layout()
        output_file = os.path.join(output_dir, f"{metric_type.lower()}_{metric}_by_year.png")
        fig.savefig(output_file)
        print(f"Plot saved to {output_file}")
        if show:
            plt.show()

def save_metrics_with_version_check(df, path, version):
    if os.path.exists(path):
        existing = pd.read_csv(path)

        if version != "v99.99.99" and version in existing["version"].unique():
            raise ValueError(f"Error: version {version} already exists in {path}.")

        if version == "v99.99.99":
            existing = existing[existing["version"] != "v99.99.99"]

        df = pd.concat([existing, df], ignore_index=True)

    df["version_sort"] = df["version"].apply(version_key)
    df = df.sort_values("version_sort", ascending=False).drop(columns=["version_sort"])

    latest_versions = sorted(df["version"].unique(), key=version_key, reverse=True)[:5]
    df = df[df["version"].isin(latest_versions)]

    df.to_csv(path, index=False)


def main(args):
    runner = ProtocolValidationRunner(
        annotated_data=args.annotated_data,
        estimate_path=args.estimate_path,
        show=args.show,
        use_pool=args.use_pool,
        num_processes=args.num_processes
    )
    runner.setup()

    base_path = os.path.join(runner.estimate_path, "record-dates")
    record_dir = os.path.join(base_path, "record-level")
    protocol_dir = os.path.join(base_path, "protocol-level")
    os.makedirs(record_dir, exist_ok=True)
    os.makedirs(protocol_dir, exist_ok=True)

    df = runner.df.copy()
    df['pdf_url'] = df['pdf_url'].apply(extract_relative_path)
    grouped = [(protocol, group) for protocol, group in df.groupby('pdf_url')]

    if runner.pool is not None:
        results = runner.pool.map(process_protocol, grouped)
    else:
        results = [process_protocol(g) for g in grouped]

    runner.missing_in_xml_all = [item for sublist in results for item in sublist[0]]
    runner.extra_in_xml_all = [item for sublist in results for item in sublist[1]]
    runner.protocol_level_results = [item[2] for item in results]

    if runner.missing_in_xml_all:
        pd.DataFrame(runner.missing_in_xml_all).to_csv(os.path.join(record_dir, "missing_annotations_fn.csv"), index=False)
    if runner.extra_in_xml_all:
        pd.DataFrame(runner.extra_in_xml_all).to_csv(os.path.join(record_dir, "wrong_annotations_fp.csv"), index=False)

    metrics_per_year, overall_metrics = calculate_record_level_metrics(
        runner.missing_in_xml_all, runner.extra_in_xml_all, df
    )
    record_df = pd.DataFrame([{'version': args.version, 'year': y, **stats} for y, stats in metrics_per_year.items()])
    save_metrics_with_version_check(record_df, os.path.join(record_dir, "record_metrics.csv"), args.version)
    plot_metrics(os.path.join(record_dir, "record_metrics.csv"), record_dir, "Record-Level", show=runner.show)

    protocol_per_year_metrics, protocol_overall_metrics = calculate_protocol_level_metrics(runner.protocol_level_results)
    protocol_df = pd.DataFrame([{'version': args.version, 'year': y, **stats} for y, stats in protocol_per_year_metrics.items()])
    save_metrics_with_version_check(protocol_df, os.path.join(protocol_dir, "protocol_metrics.csv"), args.version)
    plot_metrics(os.path.join(protocol_dir, "protocol_metrics.csv"), protocol_dir, "Protocol-Level", show=runner.show)

    overall_df = pd.DataFrame([{
        'version': args.version,
        'precision': overall_metrics['precision'],
        'recall': overall_metrics['recall'],
        'f1': overall_metrics['f1'],
        'avg_jaccard': protocol_overall_metrics['avg_jaccard'],
        'accuracy': protocol_overall_metrics['accuracy'],
        'coverage': protocol_overall_metrics['coverage']
    }])
    save_metrics_with_version_check(overall_df, os.path.join(base_path, "overall_metrics.csv"), args.version)

    print("\n=== Record-Level Overall Metrics ===")
    print(f"Precision : {overall_metrics['precision']:.4f}")
    print(f"Recall    : {overall_metrics['recall']:.4f}")
    print(f"F1 Score  : {overall_metrics['f1']:.4f}")
    print("\n=== Protocol-Level Overall Metrics ===")
    print(f"Average Jaccard : {protocol_overall_metrics['avg_jaccard']:.4f}")
    print(f"Accuracy        : {protocol_overall_metrics['accuracy']:.4f}")
    print(f"Coverage        : {protocol_overall_metrics['coverage']:.4f}\n")

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
        default="quality/estimates",
        help="Directory to save results (default: %(default)s)"
    )
    parser.add_argument("--show", action="store_true", help="Show plots interactively")
    parser.add_argument("--num_processes", type=int, default=4, help="Number of parallel processes")
    parser.add_argument("--use-pool", action="store_false", help="Use multiprocessing (only if set)")    
    parser.add_argument("--version", type=str, default="v99.99.99", help="Version tag for this run (default: v99.99.99)")
    args = parser.parse_args()

    main(args)
