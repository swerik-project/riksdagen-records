#!/usr/bin/env python3
"""
Estimate and plot the coverage of identified speakers in parliamentary protocols.

This script calculates the fraction of known versus unknown speaker attributions
and plots coverage per year for the latest versions.
"""
import matplotlib.pyplot as plt
import os
from pyriksdagen.args import (
    fetch_parser,
    impute_args
)
from qe import (
    QualityEstimator, 
    version_number_is_valid
)
from speaker_mapping_coverage import protocol_speaker_mapping_counts

def accuracy(protocol_path: str, gold_standard = None):
    """
    Compute counts of known and unknown speaker attributions for a protocol.

    Returns:
        year_code (int), known (int), unknown (int)
    """
    return protocol_speaker_mapping_counts(protocol_path)

def main(args):
        
    qe_estimator = QualityEstimator(
        records=args.records,
        estimate_path=args.estimate_path,
        version=version_number_is_valid(args.version),
        show=args.show
    )
    qe_estimator.run(estimate_func = accuracy, title="speaker-mapping-coverage", column_list = ["known", "unknown"], bounds = False)


if __name__ == "__main__":
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
    main(impute_args(args))
