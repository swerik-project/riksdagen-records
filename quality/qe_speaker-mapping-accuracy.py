#!/usr/bin/env python3
"""
Estimate accuracy of speaker-speech mapping based on a manually annotated sample.

This script compares predicted 'who' attributes in XML protocol files with a
gold-standard annotation and produces:
- CSV summary per year (difference.csv, versioned; only v99.99.99 is overwritten)
- Line plot of accuracy for the latest versions
"""

import os
import pandas as pd
from pyriksdagen.args import fetch_parser, impute_args
from pyriksdagen.utils import elem_iter, infer_metadata
from pyriksdagen.io import parse_tei
from qe import QualityEstimator

def accuracy(protocol_path: str):
    """
    Count correct and incorrect 'who' attributes according to the gold standard.
    
    Checks each note element and compares predicted 'who' attributes in child
    elements with the gold-standard person ID.
    """
    global gold_standard
    df = gold_standard

    root, ns = parse_tei(protocol_path)
    metadata = infer_metadata(protocol_path)
    year_code = int(str(metadata.get("year"))[:4])

    actual_swerik_id = None
    found_correct_element = False
    correct, incorrect = 0, 0
    ids = set(df["elem_id"])

    for tag, elem in elem_iter(root):
        # Check 'who' attributes in child elements if previous note element found
        if found_correct_element and "who" in elem.attrib:
            predicted_swerik_id = elem.attrib.get("who", None)
            if predicted_swerik_id == actual_swerik_id:
                correct += 1
            else:
                incorrect += 1
            found_correct_element = False

        # Locate note elements from gold standard
        if tag == "note" and not found_correct_element:
            elem_id = elem.attrib.get(f'{ns["xml_ns"]}id', None)
            if elem_id in ids:
                actual_swerik_id = df[df["elem_id"] == elem_id]["person_id"].iloc[0]
                found_correct_element = True

    return year_code, correct, incorrect


if __name__ == "__main__":
    # -----------------------
    # Parse command-line args
    # -----------------------
    parser = fetch_parser("records", docstring=__doc__)
    parser.add_argument(
        "-d", "--annotated-data",
        type=str,
        default="quality/data/speaker-mapping/speaker-mapping-gold-standard.csv",
        help="Path to annotated OCR quality-control data"
    )
    parser.add_argument(
        "-o", "--estimate-path",
        type=str,
        default="quality/estimates/speaker-mapping-accuracy",
        help="Path where the current estimate will be written"
    )
    parser.add_argument("-v", "--version", type=str, default="v99.99.99")
    parser.add_argument("--show", type=str, default="True")
    args = parser.parse_args()
    args.show = not args.show.lower().startswith("f")
    args = impute_args(args)

    # Ensure estimate directory exists
    os.makedirs(args.estimate_path, exist_ok=True)

    # Load gold standard once (visible to accuracy())
    gold_standard = pd.read_csv(args.annotated_data)

    # Prepare QualityEstimator
    qe_estimator = QualityEstimator(
        records=[],  # will be filled after path preparation
        estimate_path=args.estimate_path,
        version=args.version,
        show=args.show
    )

    # Prepare records list from gold standard
    gold_standard["protocol_id"] = gold_standard["protocol_id"].apply(qe_estimator.pathize_protocol_id)
    qe_estimator.records = list(gold_standard["protocol_id"].unique())

    # Validate version and run the accuracy pipeline
    qe_estimator.version = qe_estimator.validate_version()
    qe_estimator.calculate_accuracy(accuracy, column_list=["correct", "incorrect"], bounds=True)
    qe_estimator.update_difference()
    qe_estimator.plot_versions(f"{args.estimate_path}/speaker-mapping-accuracy.png")

    # Optionally show plots
    if args.show:
        import matplotlib.pyplot as plt
        plt.show()

    # Clean up resources
    qe_estimator.teardown()
    del gold_standard