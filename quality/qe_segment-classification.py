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
)
from scipy.stats import beta
from tqdm import tqdm
import os
import pandas as pd
import re
from pathlib import Path
import warnings
import editdistance
from trainerlog import get_logger

LOGGER = get_logger("QE-note-seg")

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


def length_equality(t1, t2):
    t1 = t1.strip()
    t2 = t2.strip()
    if t1 is None or t2 is None:
        return False
    minlen = min(len(t1), len(t2))
    maxlen = max(len(t1), len(t2))

    condition = maxlen / minlen <= 1.11 or minlen <= 11
    if not condition:
        LOGGER.warning(f"maxlen vs minlen: {maxlen}, {minlen}")
    return condition

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
    idmap = {t: i for t,i in zip(df["elem_id"], df["text"])}
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
                    t = idmap[x]
                    results = match_elem(subelem, df, ns)
                    correct += results[0]
                    incorrect += results[1]
                    if not length_equality(t, subelem_text):
                        LOGGER.warning(f"Ref  : {t}")
                        LOGGER.warning(f"Found: {subelem_text}")

                elif subelem_text in texts and not use_ids:
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
                t = idmap[x]
                results = match_elem(elem, df, ns)
                correct += results[0]
                incorrect += results[1]
                if not length_equality(t, elem_text):
                    LOGGER.warning(f"Ref  : {t}")
                    LOGGER.warning(f"Found: {elem_text}")
            elif elem_text in texts and not use_ids:
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
        LOGGER.error(f"No IDs matched in: {protocol}")
    return correct, incorrect

def get_old_id(record):
    record_id = Path(record).stem.split(".xml")[0]
    record_start = "-".join(record_id.split("-")[:-1])
    try:
        record_number = int(record_id.split("-")[-1])
        return f"{record_start}-{record_number}"
    except Exception:
        LOGGER.error(f"Whoops: {record}")

def main(args):
    rows = []
    correct, incorrect = 0, 0
    df = pd.read_csv(args.annotated_data)
    #records = list(df["protocol_id"].unique())
    print(df)
    LOGGER.info(f"ID matching: {not args.fuzzy}")
    LOGGER.info(f"Fuzzy matching: {args.fuzzy}")
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
    byyear_sum.to_csv(f"{args.estimate_path}/{args.estimate_filename}", index=False)




if __name__ == '__main__':
    parser = fetch_parser("records", docstring=__doc__)
    parser.add_argument("-d", "--annotated-data",
                        type=str,
                        default="quality/data/segment-classification/segment-classification.csv",
                        help="Path to annotated segment classification quality-control data")
    parser.add_argument("-o", "--estimate-path",
                        type=str,
                        default="quality/estimates/segment-classification",
                        help="Folder where the current estimate will be written")
    parser.add_argument("--estimate-filename",
                        type=str,
                        default="segment-classification-estimate-byyear-sum.csv",
                        help="Filename where the current estimate will be written")
    parser.add_argument("--fuzzy",
                        type=bool,
                        default=False,
                        help="Whether to use fuzzy text matching instead of IDs")
    args = impute_args(parser.parse_args())
    #print(args)
    main(args)
