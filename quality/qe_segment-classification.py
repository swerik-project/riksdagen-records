#!/usr/bin/env python3
"""
Estimate quality of segment classification.

.. include:: docs/qe_speaker-mapping.md
"""
from pyriksdagen.args import (
    fetch_parser,
    impute_args,
)
from pyriksdagen.utils import (
    elem_iter,
    infer_metadata,
    parse_tei,
    XML_NS,
    TEI_NS
#    pathize_protocol_id,
)
from scipy.stats import beta
from tqdm import tqdm
import os
import pandas as pd
import re
from pathlib import Path
import warnings
import editdistance

# rm after fn released in pyriksdagen
def pathize_protocol_id(protocol_id):
    """
    Turn the protocol id into a path string
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
    Check if annotated tag matches tag in protocol.
    """
    elem_id = elem.attrib.get(f'{ns["xml_ns"]}id', None)
    df_elem = df[df["elem_id"] == elem_id]
    assert len(df_elem) == 1

    annotated_tag = list(df_elem["segmentation"])[0]

    elem_tag = elem.tag.split("}")[-1]
    if elem_tag == "seg":
        elem_tag = "u"
    if elem.attrib.get("type") == "speaker":
        elem_tag = "intro"
    if annotated_tag in ["title", "margin"]:
        annotated_tag = "note"

    if type(annotated_tag) == float or annotated_tag not in ["intro", "u", "note"]:
        print("Invalid annotation:", annotated_tag)
        return 0,0

    if annotated_tag == elem_tag:
        return 1,0
    else:
        print("Error:", annotated_tag, elem_tag)
        return 0,1


def fuzzy_equality(t1, t2):
    equal = True
    if len(t1) * 0.91 <= len(t2) and len(t1) * 1.09 >= len(t2):
        dist = editdistance.eval(t1, t2)
        if dist / min(len(t1), len(t2)) > 0.15:
            equal = False
        if dist / min(len(t1), len(t2)) > 0.1 and min(len(t1), len(t2)) > 20:
            equal = False
        if dist >= 13:
            equal = False
    else:
        equal = False
    return equal

# Fix parallellization
def estimate_accuracy(protocol, df, use_ids=True):
    """
    Return correct / incorrect counts of (mis)matched segments.
    """
    root, ns = parse_tei(protocol)
    correct, incorrect = 0, 0
    ids = set(df["elem_id"])
    texts = set(df["text"])
    #print(texts)

    textmap = {t: i for t,i in zip(df["text"], df["elem_id"])}
    #exit()
    for tag, elem in elem_iter(root):
        if tag == "u":
            x = None
            for subelem in elem:
                x = subelem.attrib.get(f'{ns["xml_ns"]}id', None)
                subelem_text = None
                if subelem.text is not None:
                    subelem_text = " ".join(subelem.text.split())
                if x in ids and use_ids:
                    results = match_elem(subelem, df, ns)
                    correct += results[0]
                    incorrect += results[1]

                elif subelem_text in texts:
                    newid = textmap[subelem_text]
                    subelem.attrib[f'{XML_NS}id'] = newid
                    results = match_elem(subelem, df, ns)
                    correct += results[0]
                    incorrect += results[1]

                    texts.remove(subelem_text)

                elif subelem_text is not None and not use_ids:
                    for t in list(texts):
                        if fuzzy_equality(t, subelem_text):
                            newid = textmap[t]
                            subelem.attrib[f'{XML_NS}id'] = newid
                            results = match_elem(subelem, df, ns)
                            correct += results[0]
                            incorrect += results[1]
                            texts.remove(t)

        elif tag in ["note"]:
            x = elem.attrib.get(f'{ns["xml_ns"]}id', None)
            elem_text = None
            if elem.text is not None:
                elem_text = " ".join(elem.text.split())
            if x in ids and use_ids:
                results = match_elem(elem, df, ns)
                correct += results[0]
                incorrect += results[1]
            elif elem_text in texts:
                newid = textmap[elem_text]
                elem.attrib[f'{XML_NS}id'] = newid
                results = match_elem(elem, df, ns)
                correct += results[0]
                incorrect += results[1]

                texts.remove(elem_text)
            elif elem_text is not None and not use_ids:
                for t in list(texts):
                    if fuzzy_equality(t, elem_text):
                        newid = textmap[t]
                        elem.attrib[f'{XML_NS}id'] = newid
                        results = match_elem(elem, df, ns)
                        correct += results[0]
                        incorrect += results[1]
                        texts.remove(t)

    if correct + incorrect == 0:
        warnings.warn(f"No IDs matched in: {protocol}")
    return correct, incorrect

def get_old_id(record):
    record_id = Path(record).stem.split(".xml")[0]
    record_start = "-".join(record_id.split("-")[:-1])
    try:
        record_number = int(record_id.split("-")[-1])
        return f"{record_start}-{record_number}"
    except Exception:
        warnings.warn(f"Whoops: {record}")

def main(args):
    rows = []
    correct, incorrect = 0, 0
    df = pd.read_csv(args.annotated_data)
    df["protocol_id"] = df["protocol_id"]#.apply(lambda x: pathize_protocol_id(x))
    #records = list(df["protocol_id"].unique())
    print(df)
    print("USE FUZZY MATCHING", args.fuzzy)
    records = args.records
    for record in tqdm(records):
        record_id = get_old_id(record)
        df_p = df[df["protocol_id"] == record_id]
        if len(df_p) >= 1:
            #print(df_p)
            #exit()
            metadata = infer_metadata(record)
            acc = estimate_accuracy(record, df_p, use_ids=not args.fuzzy)
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
    parser = fetch_parser("records", docstring=__doc__)
    parser.add_argument("-d", "--annotated-data",
                        type=str,
                        default="quality/data/segment-classification/segment-classification.csv",
                        help="Path to annotated segment classification quality-control data")
    parser.add_argument("-o", "--estimate-path",
                        type=str,
                        default="quality/estimates/segment-classification",
                        help="Path where the current estimate will be written")
    parser.add_argument("--fuzzy",
                        type=bool,
                        default=False,
                        help="Whether to use fuzzy text matching instead of IDs")
    args = impute_args(parser.parse_args())
    #print(args)
    main(args)
