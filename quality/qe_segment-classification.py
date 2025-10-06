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
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pyriksdagen.args import (
    fetch_parser,
    impute_args
)
from pyriksdagen.io import parse_tei
from pyriksdagen.utils import (
    elem_iter,
    infer_metadata,
    #version_number_is_valid - next release cycle
)
from quality.qe import (
    QualityEstimator, 
    version_number_is_valid
)

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

    if elem_tag == "seg":
        elem_tag = "u"
    if elem.attrib.get("type") == "speaker":
        elem_tag = "intro"
    if annotated_tag in ["title", "margin"]:
        annotated_tag = "note"

    ignored_tags = [
        "unknown", "title, u", "title eller margin", "",
        "u, margin", "margin, intro", "seg/note", "u/intro", "?"
    ]
    if annotated_tag in ignored_tags:
        return 0, 0

    return (1, 0) if annotated_tag == elem_tag else (0, 1)

def accuracy(protocol_path: str, gold_standard):
    """
    Compute correct and incorrect segment classifications for a protocol.

    Args:
        protocol_path: Path to the XML protocol file.

    Returns:
        Tuple: (year_code, correct_count, incorrect_count)
    """
    df = gold_standard

    root, ns = parse_tei(protocol_path)
    metadata = infer_metadata(protocol_path)
    year_code = int(str(metadata.get("year"))[:4])

    correct, incorrect = 0, 0
    ids = set(df["elem_id"])

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

def main(args):
    os.makedirs(args.estimate_path, exist_ok=True)

    gold_standard = pd.read_csv(args.annotated_data)

    qe_estimator = QualityEstimator(
        records=[],
        estimate_path=args.estimate_path,
        version=version_number_is_valid(args.version),
        show=args.show
    )

    gold_standard["protocol_id"] = gold_standard["protocol_id"].apply(qe_estimator.pathize_protocol_id)
    qe_estimator.records = list(gold_standard["protocol_id"].unique())
    qe_estimator.gold_standard = gold_standard

    qe_estimator.run(estimate_func = accuracy, title="segment-classification-accuracy", column_list = ["correct", "incorrect"], bounds = True)


if __name__ == "__main__":
    parser = fetch_parser("records", docstring=__doc__)
    parser.add_argument(
        "-d", "--annotated-data",
        type=str,
        default="quality/data/segment-classification/segment-classification.csv",
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
    main(impute_args(args))
