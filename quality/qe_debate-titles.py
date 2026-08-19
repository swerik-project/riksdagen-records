#!/usr/bin/env python3
"""
Estimate debate-title correctness on expert-annotated sampled pages.

The sampling unit is a protocol page. Expert rows with a blank `titles` value
are treated as missing annotation and excluded from the coverage denominator.
For annotated rows, this script compares expert headers with
`<note type="title">` elements found on the same XML page. A row is correct
when the number of expert and XML titles is the same and every normalized
expert title has a close normalized XML match.
"""
import argparse
import os
import re
import sys
import unicodedata
from collections import defaultdict

import pandas as pd
from scipy.stats import beta

os.environ.setdefault("MPLBACKEND", "Agg")
os.environ.setdefault("MPLCONFIGDIR", "/tmp/riksdagen-records-mpl")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import matplotlib.pyplot as plt
from pyriksdagen.io import parse_tei
from pyriksdagen.utils import infer_metadata, pathize_protocol_id
from qe import QualityEstimator, version_number_is_valid


XML_ID = "{http://www.w3.org/XML/1998/namespace}id"
TEI_NS = "{http://www.tei-c.org/ns/1.0}"
NO_HEADER_VALUES = {"no header", "[no header]", "no headers"}


def normalize_space(text):
    return " ".join(str(text).split())


def normalize_title(text):
    text = unicodedata.normalize("NFKC", normalize_space(text)).casefold()
    return re.sub(r"[\s.;:,-]+$", "", text)


def levenshtein_distance(left, right):
    if left == right:
        return 0
    if len(left) < len(right):
        left, right = right, left

    previous_row = list(range(len(right) + 1))
    for i, left_char in enumerate(left, start=1):
        current_row = [i]
        for j, right_char in enumerate(right, start=1):
            insertions = previous_row[j] + 1
            deletions = current_row[j - 1] + 1
            substitutions = previous_row[j - 1] + (left_char != right_char)
            current_row.append(min(insertions, deletions, substitutions))
        previous_row = current_row
    return previous_row[-1]


def titles_match(expert_title, xml_title):
    expert_norm = normalize_title(expert_title)
    xml_norm = normalize_title(xml_title)
    if not expert_norm or not xml_norm:
        return False
    distance = levenshtein_distance(expert_norm, xml_norm)
    allowed_edits = max(1, round(max(len(expert_norm), len(xml_norm)) * 0.05))
    return distance <= allowed_edits


def title_lists_match(expert_titles, xml_titles):
    expert_list = split_titles(expert_titles)
    xml_list = [item["title"] for item in xml_titles]
    if len(expert_list) != len(xml_list):
        return False

    unmatched_xml = list(xml_list)
    for expert_title in expert_list:
        for index, xml_title in enumerate(unmatched_xml):
            if titles_match(expert_title, xml_title):
                unmatched_xml.pop(index)
                break
        else:
            return False
    return True


def split_titles(text):
    return [
        normalize_space(part)
        for part in str(text).split(";")
        if normalize_space(part)
    ]


def page_number_from_link(link):
    patterns = [
        r"[#?&]page=(\d+)",
        r"_(\d+)(?:\D*)$",
        r"-(\d+)\.jp2",
    ]
    for pattern in patterns:
        match = re.search(pattern, link)
        if match:
            return int(match.group(1))
    return None


def next_logical_page(current_page_number, observed_page_number):
    """Track page order while ignoring implausible repeated OCR page links."""
    if observed_page_number is None:
        return current_page_number
    if current_page_number is None:
        return 1 if observed_page_number > 10 else observed_page_number
    if current_page_number <= observed_page_number <= current_page_number + 5:
        return observed_page_number
    return current_page_number


def title_page_index(protocol_path):
    root, _ = parse_tei(protocol_path)
    body = root.find(f".//{TEI_NS}body")
    by_exact = defaultdict(list)
    by_page_number = defaultdict(list)
    by_logical_page_number = defaultdict(list)
    current_facs = None
    current_page_number = None
    current_logical_page_number = None

    if body is None:
        return by_exact, by_page_number, by_logical_page_number

    for elem in body.iter():
        tag = elem.tag.split("}")[-1]
        if tag == "pb":
            current_facs = elem.attrib.get("facs", "")
            current_page_number = page_number_from_link(current_facs)
            current_logical_page_number = next_logical_page(
                current_logical_page_number,
                current_page_number,
            )
            continue
        if tag != "note" or elem.attrib.get("type") != "title":
            continue

        parent = elem.getparent()
        title = normalize_space(" ".join(elem.itertext()))
        record = {
            "xml_id": elem.attrib.get(XML_ID, ""),
            "title": title,
            "page_facs": current_facs or "",
            "page_number": current_page_number,
            "logical_page_number": current_logical_page_number,
            "section_type": parent.attrib.get("type", "") if parent is not None else "",
            "section_id": parent.attrib.get(XML_ID, "") if parent is not None else "",
        }
        if current_facs:
            by_exact[current_facs].append(record)
        if current_page_number is not None:
            by_page_number[current_page_number].append(record)
        if current_logical_page_number is not None:
            by_logical_page_number[current_logical_page_number].append(record)

    return by_exact, by_page_number, by_logical_page_number


def page_titles(sample_link, by_exact, by_page_number, by_logical_page_number):
    if sample_link in by_exact:
        return by_exact[sample_link]
    page_number = page_number_from_link(sample_link)
    if page_number is None:
        return []
    return by_page_number.get(page_number, []) or by_logical_page_number.get(page_number, [])


def classify_row(expert_titles, xml_titles):
    expert_value = normalize_space(expert_titles)
    if not expert_value:
        return "missing_annotation", None

    expert_has_header = expert_value.casefold() not in NO_HEADER_VALUES
    xml_has_title = bool(xml_titles)

    if not expert_has_header and not xml_has_title:
        return "true_negative", True
    if not expert_has_header and xml_has_title:
        return "false_positive", False
    if expert_has_header and not xml_has_title:
        return "false_negative", False

    if title_lists_match(expert_value, xml_titles):
        return "true_positive_text_match", True
    return "true_positive_text_mismatch", False


def accuracy(protocol_path, gold_standard):
    """
    Count page-level debate-title correctness matches for one protocol.

    Blank expert annotations are missing data and are excluded from both
    correct and incorrect counts.
    """
    df = gold_standard[gold_standard["xml_path"] == protocol_path]
    metadata = infer_metadata(protocol_path)
    year_code = int(str(metadata.get("year"))[:4])
    indexes = title_page_index(protocol_path)

    correct, incorrect = 0, 0
    for row in df.itertuples(index=False):
        expert_titles = normalize_space(row.titles)
        if not expert_titles:
            continue
        xml_titles = page_titles(normalize_space(row.link), *indexes)
        _, title_correct = classify_row(expert_titles, xml_titles)
        if title_correct:
            correct += 1
        else:
            incorrect += 1

    return year_code, correct, incorrect


def update_decade_difference(decade_df, estimate_path, version):
    diff_path = os.path.join(estimate_path, "decade_difference.csv")
    if os.path.exists(diff_path):
        existing = pd.read_csv(diff_path)
        if version == "v99.99.99":
            existing = existing[existing["version"] != "v99.99.99"]
            combined = pd.concat([existing, decade_df], ignore_index=True)
        elif version in existing["version"].unique():
            print(f"Version {version} already exists in {diff_path}, skipping append.")
            combined = existing
        else:
            combined = pd.concat([existing, decade_df], ignore_index=True)
    else:
        combined = decade_df

    combined.to_csv(diff_path, index=False)


def write_decade_estimates(estimate_path, version):
    by_year = pd.read_csv(os.path.join(estimate_path, "upper_bound.csv"))
    by_year = by_year[(by_year["correct"] + by_year["incorrect"]) > 0].copy()
    by_year["decade"] = (by_year["year"] // 10) * 10
    decade_df = (
        by_year
        .groupby("decade", as_index=False)[["correct", "incorrect"]]
        .sum()
    )
    decade_df.insert(0, "version", version)
    total = decade_df["correct"] + decade_df["incorrect"]
    decade_df["accuracy"] = decade_df["correct"] / total
    decade_df["lower"] = decade_df.apply(
        lambda r: beta.ppf(0.05, r["correct"] + 1, r["incorrect"] + 1),
        axis=1,
    )
    decade_df["upper"] = decade_df.apply(
        lambda r: beta.ppf(0.95, r["correct"] + 1, r["incorrect"] + 1),
        axis=1,
    )
    decade_df.to_csv(os.path.join(estimate_path, "decade_bound.csv"), index=False)
    update_decade_difference(decade_df, estimate_path, version)


def plot_decade_versions(estimate_path, show=False, n_versions=6):
    diff_path = os.path.join(estimate_path, "decade_difference.csv")
    if not os.path.exists(diff_path):
        print(f"Decade difference file {diff_path} not found. Cannot plot.")
        return

    df = pd.read_csv(diff_path)
    df["version"] = df["version"].astype(str).str.strip()
    valid_versions = [v for v in df["version"].unique() if "rc" not in v.lower()]
    version_sorted = sorted(
        valid_versions,
        key=QualityEstimator.version_key,
        reverse=True,
    )[:n_versions]

    fig, ax = plt.subplots(figsize=(12, 6))
    colors = list("bgrcmyk")
    for i, version in enumerate(version_sorted):
        dfv = df[df["version"] == version].sort_values("decade")
        if dfv.empty:
            continue
        gap = dfv["decade"].diff().fillna(10) > 10
        for segment_number, (_, segment) in enumerate(dfv.groupby(gap.cumsum())):
            ax.plot(
                segment["decade"],
                segment["accuracy"],
                linewidth=1.75,
                label=version if segment_number == 0 else None,
                color=colors[i % len(colors)],
            )

    ax.set_title("debate-title-correctness by decade")
    ax.set_xlabel("Beginning of decade")
    ax.set_ylabel("Accuracy")
    ax.legend(loc="upper left")
    fig.tight_layout()
    fig.savefig(os.path.join(estimate_path, "debate-title-correctness-decade.png"))

    if show:
        fig.show()
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "-d", "--annotated-data",
        default="quality/data/debate-titles/sample-title-quality.csv",
        help="Path to expert-annotated debate title sample CSV.",
    )
    parser.add_argument(
        "-o", "--estimate-path",
        default="quality/estimates/debate-titles",
        help="Directory where estimate outputs are written.",
    )
    parser.add_argument(
        "-v", "--version",
        default="v99.99.99",
        help="Version string for this run.",
    )
    parser.add_argument(
        "--show",
        default="False",
        help="Whether to show the plot interactively (True/False).",
    )
    args = parser.parse_args()
    args.show = not args.show.lower().startswith("f")
    version = version_number_is_valid(args.version)
    os.makedirs(args.estimate_path, exist_ok=True)

    gold_standard = pd.read_csv(args.annotated_data, keep_default_na=False)
    gold_standard["protocol_id"] = gold_standard["protocol_id"].apply(normalize_space)
    gold_standard["link"] = gold_standard["link"].apply(normalize_space)
    gold_standard["titles"] = gold_standard["titles"].apply(normalize_space)
    gold_standard["xml_path"] = gold_standard["protocol_id"].apply(pathize_protocol_id)

    qe_estimator = QualityEstimator(
        records=list(gold_standard["xml_path"].unique()),
        estimate_path=args.estimate_path,
        version=version,
        show=args.show,
    )
    qe_estimator.gold_standard = gold_standard
    qe_estimator.run(
        estimate_func=accuracy,
        title="debate-title-correctness",
        column_list=["correct", "incorrect"],
        bounds=True,
    )
    write_decade_estimates(args.estimate_path, version)
    plot_decade_versions(args.estimate_path, show=args.show)


if __name__ == "__main__":
    main()
