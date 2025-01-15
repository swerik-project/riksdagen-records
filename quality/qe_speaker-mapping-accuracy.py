#!/usr/bin/env python3
"""
Estimate accuracy of speaker-speech mapping based on a manually annotated sample.

.. include:: docs/qe_speaker-mapping-accuracy.md
"""
from pyriksdagen.args import (
    fetch_parser,
    impute_args,
)
from pyriksdagen.utils import (
    elem_iter,
    infer_metadata,
    parse_tei,
#    pathize_protocol_id,  # to appear in next version of pyriksdagen
)
from scipy.stats import beta
from tqdm import tqdm
import os
import pandas as pd
import re



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


def estimate_accuracy(protocol, df):
    """
    Count correct and incorrect who attribs according to the gold standard.
    """
    root, ns = parse_tei(protocol)

    actual_swerik_id = None
    found_correct_element=False
    correct, incorrect = 0, 0
    ids = set(df["elem_id"])

    for tag, elem in elem_iter(root):
        if found_correct_element and 'who' in elem.attrib:
            predicted_swerik_id = elem.attrib.get('who', None)  ## change to Swerik ID

            if predicted_swerik_id==actual_swerik_id:
                correct+=1
            else:
                incorrect+=1
                if predicted_swerik_id != "unknown":
                    print(predicted_swerik_id, actual_swerik_id)
            #reset boolean
            found_correct_element=False

        if tag == "note" and found_correct_element==False:
            x = elem.attrib.get(f'{ns["xml_ns"]}id', None)
            if x in ids:
                actual_swerik_id = df[df["elem_id"] == x]["person_id"].iloc[0]
                found_correct_element=True

    return correct, incorrect




def main(args):
    rows = []
    correct, incorrect = 0, 0
    df = pd.read_csv(args.annotated_data)
    df["protocol_id"] = df["protocol_id"].apply(lambda x: pathize_protocol_id(x))
    records = list(df["protocol_id"].unique())
    for record in tqdm(records):
        df_p = df[df["protocol_id"] == record]
        if len(df_p) >= 1:
            metadata=infer_metadata(record)
            acc = estimate_accuracy(record, df_p)
            correct += acc[0]
            incorrect += acc[1]
            if acc[1] + acc[0] > 0:
                rows.append([acc[0], acc[1], acc[0] / (acc[0] + acc[1]), metadata["year"], metadata["chamber"]])

    accuracy = correct / (correct + incorrect)

    lower = beta.ppf(0.05, correct + 1, incorrect + 1)
    upper = beta.ppf(0.95, correct + 1, incorrect + 1)
    print(f"ACC: {100 * accuracy:.2f}% [{100* lower:.2f}% – {100* upper:.2f}%]")
    df = pd.DataFrame(rows, columns=["correct", "incorrect", "accuracy", "year", "chamber"])
    df["decade"] = (df["year"] // 10) * 10
    print(df)
    df.to_csv(f"{args.estimate_path}/mapping-accuracy-estimate.csv", index=False)

    byyear_sum = df[["correct", "incorrect"]].groupby(df['decade']).sum()
    byyear_sum["lower"] = [beta.ppf(0.05, c + 1, i + 1) for c, i in zip(byyear_sum["correct"], byyear_sum["incorrect"])]
    byyear_sum["upper"] = [beta.ppf(0.95, c + 1, i + 1) for c, i in zip(byyear_sum["correct"], byyear_sum["incorrect"])]
    byyear = df['accuracy'].groupby(df['decade'])
    byyear_sum = byyear_sum.merge(byyear.mean(), on="decade").reset_index()
    print(byyear_sum)
    byyear_sum.to_csv(f"{args.estimate_path}/mapping-accuracy-estimate-byyear-sum.csv", index=False)




if __name__ == '__main__':
    parser = fetch_parser("records", docstring=__doc__)
    parser.add_argument("-d", "--annotated-data",
                        type=str,
                        default="quality/data/speaker-mapping/speaker-mapping-gold-standard.csv",
                        help="Path to annotated ocr quality-control data")
    parser.add_argument("-o", "--estimate-path",
                        type=str,
                        default="quality/estimates/speaker-mapping",
                        help="Path where the current estimate will be written")
    main(impute_args(parser.parse_args()))
