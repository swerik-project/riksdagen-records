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
from pyriksdagen.io import parse_tei
from pyriksdagen.utils import (
    infer_metadata,
    #version_number_is_valid - next release cycle
) 
from qe import (
    QualityEstimator, 
    version_number_is_valid
)

def accuracy(protocol_path: str, gold_standard = None):
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