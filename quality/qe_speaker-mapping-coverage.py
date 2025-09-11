#!/usr/bin/env python3
"""
Estimate and plot the coverage of identified speakers in parliamentary protocols.

This script calculates the fraction of known versus unknown speaker attributions
and plots coverage per year for the latest versions.
"""

import os
import pandas as pd
import matplotlib.pyplot as plt
from pyriksdagen.args import fetch_parser, impute_args
from pyriksdagen.io import parse_tei
from pyriksdagen.utils import infer_metadata
from qe import QualityEstimator


def accuracy(protocol_path: str):
    """
    Compute counts of known and unknown speaker attributions for a protocol.

    Returns:
        year_code (int), known (int), unknown (int)
    """
    root, ns = parse_tei(protocol_path, get_ns=True)
    metadata = infer_metadata(protocol_path)
    year_code = int(str(metadata.get("year"))[:4])

    known, unknown = 0, 0
    for div in root.findall(f".//{ns['tei_ns']}div"):
        for elem in div:
            who = elem.attrib.get("who")
            if who is not None:
                if who == "unknown":
                    unknown += 1
                else:
                    known += 1
    return year_code, known, unknown


if __name__ == "__main__":
    # -----------------------
    # Parse command-line args
    # -----------------------
    parser = fetch_parser("records", docstring=__doc__)
    parser.add_argument(
        "-o", "--estimate-path",
        type=str,
        default="quality/estimates/speaker-mapping-coverage",
        help="Path where the current estimate will be written"
    )
    parser.add_argument("-v", "--version", type=str, default="v99.99.99")
    parser.add_argument("--show", type=str, default="True")
    args = parser.parse_args()
    args.show = not args.show.lower().startswith("f")
    args = impute_args(args)
    os.makedirs(args.estimate_path, exist_ok=True)

    # -----------------------
    # Prepare records
    # -----------------------
    qe_estimator = QualityEstimator(
        records=args.records,
        estimate_path=args.estimate_path,
        version=args.version,
        show=args.show
    )

    # -----------------------
    # Run coverage calculation
    # -----------------------
    qe_estimator.version = qe_estimator.validate_version()
    qe_estimator.calculate_accuracy(accuracy, column_list=["known", "unknown"], bounds=False)

    # -----------------------
    # Save and summarize
    # -----------------------
    df_upper = qe_estimator.df_upper
    df_upper.to_csv(os.path.join(args.estimate_path, "upper_bound.csv"), index=False)
    print("Upper bound coverage summary:")
    print(df_upper)
    print("Average coverage:", df_upper["accuracy"].mean())
    total_known = df_upper["known"].sum()
    total = df_upper[["known", "unknown"]].sum().sum()
    print("Weighted average coverage:", total_known / total)
    print("Minimum coverage:", df_upper["accuracy"].min(), "at year:", df_upper["accuracy"].idxmin())

    # -----------------------
    # Plot coverage
    # -----------------------
    qe_estimator.update_difference()
    qe_estimator.plot_versions(os.path.join(args.estimate_path, "speaker-mapping-coverage.png"))

    if args.show:
        plt.show()

    # -----------------------
    # Cleanup
    # -----------------------
    qe_estimator.teardown()