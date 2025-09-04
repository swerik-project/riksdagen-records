#!/usr/bin/env python3
#!/usr/bin/env python3
"""
Estimate quality of segment classification in parliamentary protocols.

This script compares annotated segmentation tags with actual XML tags
in protocol files and estimates accuracy over time. It produces:
- CSV summary of overall results
- CSV summary by year
- Line plots of accuracy with confidence intervals

.. include:: docs/qe_speaker-mapping.md
"""
import os
import re
import unittest
import pandas as pd
import matplotlib.pyplot as plt
from scipy.stats import beta
from tqdm import tqdm

from pyriksdagen.args import fetch_parser, impute_args
from pyriksdagen.utils import elem_iter, infer_metadata, parse_tei

def ignore_tag(tag):
    """
    Determine whether a segmentation tag should be ignored in accuracy calculations.

    Args:
        tag (str): The segmentation tag by expert.

    Returns:
        bool: True if the tag is considered invalid/ignored; False otherwise.
    """
    tag = str(tag).lower()
    ignored_tags = ["unknown", 
                    "title, u", 
                    "title eller margin", 
                    "", 
                    "u, margin", 
                    "margin, intro",
                    "seg/note", 
                    "u/intro", 
                    "?"]
    return tag in ignored_tags

# rm after fn released in pyriksdagen
def pathize_protocol_id(protocol_id):
    """
    Convert a protocol ID into a filesystem path for the XML protocol.

    Args:
        protocol_id (str): Protocol identifier in standard format.

    Returns:
        str: Path to the corresponding XML file.

    Raises:
        FileNotFoundError: If the file does not exist after normalization.
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
    #print(path_)
    if os.path.exists(path_):
        return path_
    else:
        path_ = re.sub(f'((extra)?h[^-]+st|")', '', path_)
    #    print("~~~~", path_)
        if os.path.exists(path_):
            return path_
    raise FileNotFoundError(f"Can't find {path_}")


def match_elem(elem, df, ns):
    """
    Compare a TEI element's tag with its annotated segmentation tag.

    Args:
        elem (xml.etree.ElementTree.Element): XML element from protocol.
        df (pd.DataFrame): DataFrame containing annotations for the protocol.
        ns (dict): Namespace dictionary for TEI parsing.

    Returns:
        tuple[int, int]: (correct, incorrect) counts for this element.
    """

    elem_id = elem.attrib.get(f'{ns["xml_ns"]}id', None)
    df_elem = df[df["elem_id"] == elem_id]
    assert len(df_elem) == 1

    annotated_tag = str(list(df_elem["segmentation"])[0]).lower()

    # normalize elem_tag
    elem_tag = elem.tag.split("}")[-1]
    if elem_tag == "seg":
        elem_tag = "u"
    if elem.attrib.get("type") == "speaker":
        elem_tag = "intro"
    if annotated_tag in ["title", "margin"]:
        annotated_tag = "note"

    # skip ignored annotations for global accuracy
    if ignore_tag(annotated_tag):
        print(f"Ignored annotation {annotated_tag} for element {elem_id}")
        return 0, 1  # count false annotations as incorrect qe_segment classification.

    if annotated_tag == elem_tag:
        return 1, 0
    else:
        return 0, 1


def estimate_accuracy(protocol, df):
    """
    Compute correct/incorrect matches for all elements in a protocol.

    Args:
        protocol (str): Path to XML protocol file.
        df (pd.DataFrame): Annotations for the protocol.

    Returns:
        tuple[int, int]: (total_correct, total_incorrect)
    """
    root, ns = parse_tei(protocol)
    correct, incorrect = 0, 0
    ids = set(df["elem_id"])
    for tag, elem in elem_iter(root):
        if tag == "u":
            x = None
            for subelem in elem:
                x = subelem.attrib.get(f'{ns["xml_ns"]}id', None)
                if x in ids:
                    subelem_text = " ".join(subelem.text.split())
                    results = match_elem(subelem, df, ns)
                    correct += results[0]
                    incorrect += results[1]

        elif tag in ["note"]:
            x = elem.attrib.get(f'{ns["xml_ns"]}id', None)
            if x in ids:
                elem_text = " ".join(elem.text.split())
                results = match_elem(elem, df, ns)
                correct += results[0]
                incorrect += results[1]

    return correct, incorrect


class TestSegmentClassification(unittest.TestCase):


    @classmethod
    def setUpClass(cls):
        parser = fetch_parser("records", docstring=__doc__)
        parser.add_argument("-d", "--annotated-data",
                            type=str, 
                            default="quality/data/segment-classification/segment-classification.csv")
        parser.add_argument("-o", "--estimate-path",
                            type=str,
                            default="quality/estimates/segment-classification")
        args = impute_args(parser.parse_args([]))
        cls.df = pd.read_csv(args.annotated_data)
        cls.df["protocol_id"] = cls.df["protocol_id"].apply(pathize_protocol_id)
        cls.records = list(cls.df["protocol_id"].unique())
        cls.rows = []
        cls.correct = 0
        cls.incorrect = 0
        cls.estimate_path = args.estimate_path


    def test_records(self):
        """
        Process each record and accumulate correct/incorrect counts.
        Stores detailed per-record results in cls.rows.
        """
        for record in self.records:
            df_p = self.df[self.df["protocol_id"] == record]
            if len(df_p) >= 1:
                metadata = infer_metadata(record)
                acc = estimate_accuracy(record, df_p)
                type(self).correct += acc[0]
                type(self).incorrect += acc[1]
                if acc[1] + acc[0] > 0:
                    self.rows.append([
                        acc[0], acc[1], acc[0] / (acc[0] + acc[1]),
                        metadata["year"], metadata["chamber"]
                    ])

        self.assertGreaterEqual(self.correct, 0)


    @classmethod
    def tearDownClass(cls):
        total = cls.correct + cls.incorrect
        accuracy = cls.correct / (total) if total > 0 else 0
        
        lower = beta.ppf(0.05, cls.correct + 1, cls.incorrect + 1)
        upper = beta.ppf(0.95, cls.correct + 1, cls.incorrect + 1)
        print(f"Acc: {100*accuracy:.2f}% [{100*lower:.2f} - {100*upper:.2f}%]")

        df = pd.DataFrame(cls.rows, columns=["correct", "incorrect", "accuracy", "year", "chamber"])
        df.to_csv(f"{cls.estimate_path}/segment-classification-estimate.csv", index=False)

        byyear = df.groupby("year")[["correct","incorrect"]].sum().reset_index()
        byyear["accuracy"] = byyear["correct"] / (byyear["correct"] + byyear["incorrect"])
        byyear["lower"] = byyear.apply(lambda row: beta.ppf(0.05, row["correct"] + 1, row["incorrect"] + 1), axis=1)
        byyear["upper"] = byyear.apply(lambda row: beta.ppf(0.95, row["correct"] + 1, row["incorrect"] + 1), axis=1)
        byyear.to_csv(f"{cls.estimate_path}/segment-classification-estimate-byyear.csv", index=False)

        plt.figure(figsize=(10,5))
        plt.plot(byyear["year"], byyear["accuracy"], linestyle='-', color='blue', label="Accuracy")
        plt.fill_between(byyear["year"], byyear["lower"], byyear["upper"], color='blue', alpha=0.2)
        plt.xlabel("Year")
        plt.ylabel("Accuracy")
        plt.title("Segment Classification Accuracy per Year")
        plt.xticks(rotation=45)
        plt.legend()
        plt.tight_layout()
        plt.savefig(f"{cls.estimate_path}/segment-classification-accuracy-by-year.png")
        plt.close()


def main(args):
    rows = []
    correct, incorrect = 0, 0
    df = pd.read_csv(args.annotated_data)
    df["protocol_id"] = df["protocol_id"].apply(lambda x: pathize_protocol_id(x))
    records = list(df["protocol_id"].unique())
    for record in tqdm(records):
        df_p = df[df["protocol_id"] == record]
        if len(df_p) >= 1:
            metadata = infer_metadata(record)
            acc = estimate_accuracy(record, df_p)
            correct += acc[0]
            incorrect += acc[1]
            if acc[1] + acc[0] > 0:
                rows.append([acc[0], acc[1], acc[0] / (acc[0] + acc[1]), metadata["year"], metadata["chamber"]])

    accuracy = correct / (correct + incorrect)

    lower = beta.ppf(0.05, correct + 1, incorrect + 1)
    upper = beta.ppf(0.95, correct + 1, incorrect + 1)
    print(f"ACC: {100 * accuracy:.2f}% [{100* lower:.2f}% – {100* upper:.2f}%]")

    print(correct, incorrect)

    df = pd.DataFrame(rows, columns=["correct", "incorrect", "accuracy", "year", "chamber"])
    df["decade"] = (df["year"] // 10) * 10
    print(df)
    df.to_csv(f"{args.estimate_path}/segment-classification-estimate.csv", index=False)

    byyear_sum = df[["correct", "incorrect"]].groupby(df['decade']).sum()
    byyear_sum["lower"] = [beta.ppf(0.05, c + 1, i + 1) for c, i in zip(byyear_sum["correct"], byyear_sum["incorrect"])]
    byyear_sum["upper"] = [beta.ppf(0.95, c + 1, i + 1) for c, i in zip(byyear_sum["correct"], byyear_sum["incorrect"])]
    byyear = df['accuracy'].groupby(df['decade'])
    byyear_sum = byyear_sum.merge(byyear.mean(), on="decade").reset_index()
    print(byyear_sum)
    byyear_sum.to_csv(f"{args.estimate_path}/segment-classification-estimate-byyear-sum.csv", index=False)


if __name__ == '__main__':
    unittest.main()
