#!/usr/bin/env python3
"""
Estimate OCR quality based on a manually annotated sample.

.. include:: docs/qe_ocr-estimation.md
"""
from glob import glob
from pyriksdagen.args import (
    fetch_parser,
    impute_args,
)
from pyriksdagen.utils import (
    elem_iter,
    parse_tei,
#   pathize_protocol_id,
)
from torchmetrics.text import WordErrorRate
from tqdm import tqdm
import argparse
import nltk
import numpy as np
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
        path_ = re.sub(f'(h[^-]+st|")', '', path_)
    #    print("~~~~", path_)
        if os.path.exists(path_):
            return path_
    raise FileNotFoundError(f"Can't find {path_}")


def get_pb_range(root, ns, facs):
    """
    From the facs attrip in the sample, get the previous and next pb elem
    """
    pre_target = None
    target = None
    post_target = None
    for dix, div in enumerate(root.findall(f".//{ns['tei_ns']}div")):
        for eix, elem in enumerate(div):
            if elem.tag == f"{ns['tei_ns']}pb":
                if target is None:
                    if elem.attrib['facs'] == facs:
                        target = (dix, eix)
                    else:
                        pre_target = (dix, eix)
                else:
                    post_target = (dix, eix)
                    break
    print((pre_target, post_target), root, ns)
    return (pre_target, post_target), root, ns


def unformat_text(text):
    """
    remove line breaks from text and join with a single space
    """
    text = ' '.join([_.strip() for _ in text.splitlines()])
    return text


def get_text_from_elem(e, text, ns):
    """
    append elem.text to text
    """
    if e.tag == f"{ns['tei_ns']}note":
        text.append(unformat_text(e.text))
    elif e.tag == f"{ns['tei_ns']}u":
        for seg in e:
            text.append(unformat_text(seg.text))
    return text


def get_text(_range, root, ns):
    """
    get all text between 1 pb before and 1 pb after the pb elem referenced in the sample
    """
    divs = root.findall(f".//{ns['tei_ns']}div")
    try:
        div_range = list(range(_range[0][0], _range[1][0]+1))
    except:
        try:
            div_range = list(range(_range[0][0], len(divs)))
        except:
            div_range = list(range(0, _range[1][0]+1))
    try:
        start = _range[0][1]
    except:
        start = 0
    try:
        end = _range[1][1]
    except:
        end = None
    text = []
    for ix, _ in enumerate(div_range):
        div = divs[_]
        if len(div_range) == 1:
            if end is None:
                elems = list(range(start, len(div)))
            else:
                elems = list(range(start, end))
            for elem in elems:
                e = div[elem]
                text = get_text_from_elem(e, text, ns)
        else:
            elems = None
            if ix == 0:
                elems = list(range(start, len(div)))
            elif ix == len(div_range)-1:
                if end is None:
                    elems = list(range(0, len(div)))
                else:
                    elems = list(range(0, end))
            else:
                elems = list(range(0, len(div)))
            for elem in elems:
                e = div[elem]
                text = get_text_from_elem(e, text, ns)
    return ' '.join([_.strip() for _ in text])


def get_all_text(root, ns):
    """
    get ALL text from notes and utterances in a protocol
    """
    text = []
    for tag, elem in elem_iter(root):
        text = get_text_from_elem(elem, text, ns)
    return ' '.join([_.strip() for _ in text])


def mk_string_list(l, text):
    """
    make a list of strings of len == len(annotation)
    """
    str_list = []
    start = 0
    while True:
        str_list.append(text[start:start+l+1])
        start += 1
        if start + l + 1 == len(text):
            break
    return str_list


def get_most_probable_line(annotated, text):
    """
    get the string with the lowest levenshtein distance to the annotation
    """
    most_probable_line = None
    prob = None
    str_list = mk_string_list(len(annotated), text)
    for s in str_list:
        lev = nltk.edit_distance(annotated.lower().strip(), s.lower().strip())
        if prob is None or lev < prob:
            print(" ~", prob, lev)
            prob = lev
            most_probable_line = s
            if prob == 0:
                break
            if prob == 1 and annotated.endswith('-') and not s.endswith('-'):
                break
    return most_probable_line, prob




def main(args):

    wer_fn = WordErrorRate()

    def _concat_mpl():
        # Load student-annotated data
        return pd.concat(
            [pd.read_csv(_, sep='\t') for _ in glob(f"{args.estimate_path}/lev-by-decade/*.tsv")],
            ignore_index=True).sort_values(by=["prot"], ignore_index=True)



    if args.read_lev:
        mpl_df = _concat_mpl()
    else:
        # Find most probable line and calculate lev distance
        if args.decade is not None:
            samples = glob(f"{args.annotated_data}/sample_{args.decade}_annotated.csv")
        else:
            samples = glob(f"{args.annotated_data}/*.csv")
        for sample in samples:
            decade = sample.split("_")[-2]
            print("---->", decade)

            rows = []
            cols = ["prot", "annotation", "NROWS", "NCOLS",
                    "row_to_check", "most_probable_line", "lev"]
            df = pd.read_csv(sample, sep=';')
            df["protocol_id"] = df["protocol_id"].apply(lambda x: pathize_protocol_id(x))
            for i, r in tqdm(df.iterrows(), total=len(df)):
                print(f"  ~~~~~~~~  {r['protocol_id']}  ~~~~~~~~  ")
                text = get_text(*get_pb_range(*parse_tei(r["protocol_id"]), r['facs']))
                most_probable_line, lev = get_most_probable_line(r['content'], text)

                print(r['content'])
                print(most_probable_line)
                rows.append([r["protocol_id"], r['content'], r["NROWS"], r["NCOLS"], r['row_to_check'], most_probable_line, lev])

            dec_mpl_df = pd.DataFrame(rows, columns=cols)
            dec_mpl_df.to_csv(f"{args.estimate_path}/lev-by-decade/{decade}_mpl_lev.tsv", sep='\t', index=False)


    if args.concat_lev:
        if mpl_df is None:
            mpl_df = _concat_mpl()
        mpl_df.to_csv(f"{args.estimate_path}/mpl_lev.tsv", sep='\t', index=False)


    if not args.lev_only:
        # make further calculations

        mpl_df["year"] = None
        mpl_df["decade"] = None
        mpl_df['wer'] = None
        mpl_df['cer'] = None
        for i, r in mpl_df.iterrows():
            year = int(r['prot'].split('/')[1])
            mpl_df.at[i, 'year'] = year
            mpl_df.at[i, 'decade'] = (year // 10) * 10
            if not args.skip_second_search:
                if r['lev'] > args.lev_threshold:
                    print("a.", r['lev'], r['most_probable_line'])
                    text = get_all_text(*parse_protocol(r['prot'], get_ns=True))
                    most_probable_line, lev = get_most_probable_line(r['annotation'], text)
                    print("b.", lev, most_probable_line)
                    df.at[i, "lev"] = lev
                    df.at[i, "most_probable_line"] = most_probable_line
            if args.ignore_dash:
                if r['annotation'].endswith('-'):
                    a = r['annotation'].strip()[:-1]
                    b = r['most_probable_line'].strip()[:-1]
                    mpl_df.at[i, 'annotation'] = a
                    mpl_df.at[i, 'most_probable_line'] = b
                    mpl_df.at[i, 'lev'] = nltk.edit_distance(a.lower(), b.lower())
            mpl_df.at[i, 'wer'] = float(wer_fn(r['annotation'], r['most_probable_line']))
            mpl_df.at[i, 'cer'] = r['lev']/len(r['annotation'])

        mpl_df.to_csv(f"{args.estimate_path}/mpl_lev+.tsv", sep='\t', index=False)

        print(f'average lev: {np.mean(mpl_df["lev"])}')
        print(f'quantile 1 lev: {np.quantile(mpl_df["lev"], q=0.25)}')
        print(f'quantile 3 lev: {np.quantile(mpl_df["lev"], q=0.75)}')
        print(f'average WER: {np.mean(mpl_df["wer"])}')
        print(f'quantile 1 WER: {np.quantile(mpl_df["wer"], q=0.25)}')
        print(f'quantile 3 WER: {np.quantile(mpl_df["wer"], q=0.75)}')
        print(f'average CER: {np.mean(mpl_df["cer"])}')
        print(f'quantile 1 CER: {np.quantile(mpl_df["cer"], q=0.25)}')
        print(f'quantile 3 CER: {np.quantile(mpl_df["cer"], q=0.75)}')
        print(f'fraction of perfect matches: {len(mpl_df.loc[mpl_df["lev"] == 0])/len(mpl_df)}')


        #generate summary matricies
        print("\n\n\nSummarizing...\n\n\n")

        rows = []
        decades = mpl_df['decade'].unique()
        for dec in decades:
            dec_df = mpl_df.loc[mpl_df['decade'] == dec].copy()
            rows.append([dec,
                        np.mean(dec_df['lev']),
                        np.quantile(dec_df["lev"], q=0.25),
                        np.quantile(dec_df["lev"], q=0.75),
                        np.mean(dec_df['wer']),
                        np.quantile(dec_df["wer"], q=0.25),
                        np.quantile(dec_df["wer"], q=0.75),
                        np.mean(dec_df['cer']),
                        np.quantile(dec_df["cer"], q=0.25),
                        np.quantile(dec_df["cer"], q=0.75),
                        len(dec_df.loc[dec_df['lev'] == 0])/ len(dec_df)
                        ])

        summary = pd.DataFrame(rows, columns = ["decade",
                                                "lev_mean", "lev_first_q", "lev_third_q",
                                                "wer_mean", "wer_first_q", "wer_third_q",
                                                "cer_mean", "cer_first_q", "cer_third_q",
                                                "perfect_match"])
        print(summary)
        summary.to_csv(f"{args.estimate_path}/metrics.csv", index=False)




if __name__ == '__main__':
    parser = fetch_parser("records", docstring=__doc__)
    parser.add_argument("-d", "--annotated-data",
                        type=str,
                        default="quality/data/ocr-estimation",
                        help="Path to annotated ocr quality-control data")
    parser.add_argument("-D", "--decade",
                        type=str,
                        default=None,
                        help="Calculate single decade")
    parser.add_argument("-o", "--estimate-path",
                        type=str,
                        default="quality/estimates/ocr-estimation",
                        help="Path where the current estimate will be written")
    parser.add_argument("--read-lev",
                        action='store_true',
                        help="read most probable line and levenshtein distance from a file.")
    parser.add_argument("--lev-only",
                        action='store_true',
                        help="Only calculate levenstein distances")
    parser.add_argument("--concat-lev",
                        action='store_true',
                        help="save concatenated levenstein distances")
    parser.add_argument("--skip-second-search", type=bool, default=True,
                        help="skip looking for line again when lev > lev-threshold")
    parser.add_argument("--ignore-dash",
                        action='store_true',
                        help="Recalculate dev w/out line-final dash")
    args = impute_args(parser.parse_args())
    main(args)
