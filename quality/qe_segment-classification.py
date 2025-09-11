#!/usr/bin/env python3
"""
Estimate the quality of segment classification in parliamentary protocols.

This script compares annotated segmentation tags (gold standard) with the
actual XML tags in protocol files and estimates accuracy per year. It produces:
- CSV summary per year (difference.csv, versioned; only v99.99.99 is overwritten)
- Line plot of accuracy for the latest six versions
"""

import os
import pandas as pd
from pyriksdagen.args import fetch_parser, impute_args
from pyriksdagen.utils import elem_iter, infer_metadata
from pyriksdagen.io import parse_tei
from qe import QualityEstimator

def match_elem(elem, df, ns) -> tuple:
    """
    Compare a single XML element with the annotated segmentation tag.

    Args:
        elem: XML element from the protocol.
        df: DataFrame containing gold-standard annotations.
        ns: Namespace dictionary for XML parsing.

    Returns:
        Tuple of (correct_count, incorrect_count), either (1, 0) or (0, 1),
        or (0, 0) if the element should be ignored.
    """
    elem_id = elem.attrib.get(f'{ns["xml_ns"]}id', None)
    df_elem = df[df["elem_id"] == elem_id]
    assert len(df_elem) == 1, f"Element ID {elem_id} not found in gold standard"

    annotated_tag = str(df_elem["segmentation"].iloc[0]).lower()
    elem_tag = elem.tag.split("}")[-1]

    # Normalize tags for comparison
    if elem_tag == "seg":
        elem_tag = "u"
    if elem.attrib.get("type") == "speaker":
        elem_tag = "intro"
    if annotated_tag in ["title", "margin"]:
        annotated_tag = "note"

    # Tags to ignore
    ignored_tags = [
        "unknown", "title, u", "title eller margin", "",
        "u, margin", "margin, intro", "seg/note", "u/intro", "?"
    ]
    if annotated_tag in ignored_tags:
        return 0, 0

    return (1, 0) if annotated_tag == elem_tag else (0, 1)

def accuracy(protocol_path: str):
    """
    Compute correct and incorrect segment classifications for a protocol.

    Args:
        protocol_path: Path to the XML protocol file.

    Returns:
        Tuple: (year_code, correct_count, incorrect_count)
    """
    global gold_standard
    df = gold_standard

    root, ns = parse_tei(protocol_path)
    metadata = infer_metadata(protocol_path)
    year_code = int(str(metadata.get("year"))[:4])

    correct, incorrect = 0, 0
    ids = set(df["elem_id"])

    # Iterate over elements and subelements
    for tag, elem in elem_iter(root):
        elem_id = elem.attrib.get(f'{ns["xml_ns"]}id', None)
        if elem_id in ids:
            c, i = match_elem(elem, df, ns)
            correct += c
            incorrect += i
        for subelem in elem:
            subelem_id = subelem.attrib.get(f'{ns["xml_ns"]}id', None)
            if subelem_id in ids:
                c, i = match_elem(subelem, df, ns)
                correct += c
                incorrect += i

    return year_code, correct, incorrect

if __name__ == "__main__":
    # ------------------------
    # Argument parsing
    # ------------------------
    parser = fetch_parser("records", docstring=__doc__)
    parser.add_argument(
        "-d", "--annotated-data",
        type=str,
        default="quality/data/segment-classification/segment-classification-gold-standard.csv",
        help="Path to CSV file containing gold-standard segmentation tags"
    )
    parser.add_argument(
        "-o", "--estimate-path",
        type=str,
        default="quality/estimates/segment-classification",
        help="Directory where results and plots will be saved"
    )
    parser.add_argument(
        "-v", "--version",
        type=str,
        default="v99.99.99",
        help="Version string for this run (semantic versioning)"
    )
    parser.add_argument(
        "--show",
        type=str,
        default="True",
        help="Whether to show the plot interactively (True/False)"
    )
    args = parser.parse_args()
    args.show = not args.show.lower().startswith("f")
    args = impute_args(args)

    # Ensure output directory exists
    os.makedirs(args.estimate_path, exist_ok=True)

    # ------------------------
    # Load gold standard
    # ------------------------
    gold_standard = pd.read_csv(args.annotated_data)

    # ------------------------
    # Instantiate QualityEstimator
    # ------------------------
    qe_estimator = QualityEstimator(
        records=[],
        estimate_path=args.estimate_path,
        version=args.version,
        show=args.show
    )

    # Convert protocol IDs to XML paths and set records
    gold_standard["protocol_id"] = gold_standard["protocol_id"].apply(qe_estimator.pathize_protocol_id)
    qe_estimator.records = list(gold_standard["protocol_id"].unique())

    # Validate version
    qe_estimator.version = qe_estimator.validate_version()

    # ------------------------
    # Run accuracy estimation pipeline
    # ------------------------
    qe_estimator.calculate_accuracy(
        estimate_func=accuracy,
        column_list=["correct", "incorrect"],
        bounds=False
    )
    qe_estimator.update_difference()
    qe_estimator.plot_versions(f"{args.estimate_path}/segment-classification-accuracy.png")

    # Show plot if requested
    if args.show:
        import matplotlib.pyplot as plt
        plt.show()

    # Clean up resources
    qe_estimator.teardown()
    del gold_standard
