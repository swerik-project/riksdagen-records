#!/usr/bin/env python3
"""
OCR Quality Estimation Script

This script evaluates the quality of OCRed text against annotated reference text.
It computes metrics such as:
- Levenshtein distance (LEV)
- Word Error Rate (WER)
- Character Error Rate (CER)  # case-sensitive
- Perfect match ratio (percentage of exact matches)

The script processes TEI XML protocols, aligns annotated lines with OCR segments,
aggregates metrics per year, and saves the results to a versioned CSV.
It also generates plots for CER, WER, and LEV over years across multiple versions.
"""
from functools import lru_cache
from glob import glob
import matplotlib.pyplot as plt
from multiprocessing import (
    cpu_count,
    Pool
)
import os
from packaging import version
from pathlib import Path
import pandas as pd
from pyriksdagen.args import (
    fetch_parser, 
    impute_args
)
from pyriksdagen.io import parse_tei
from pyriksdagen.utils import elem_iter
from rapidfuzz.distance import Levenshtein
import re
from tqdm import tqdm

@lru_cache(maxsize=256)
def cached_parse_tei(path_or_id: str):
    """Parse TEI XML and cache result per process to avoid repeated parsing of the same file."""
    return parse_tei(path_or_id)


@lru_cache(maxsize=256)
def get_pb_positions(path_or_id):
    """Return cached list of (div_index, elem_index) positions of <pb> tags."""
    root, ns = cached_parse_tei(path_or_id)
    positions = []
    divs = list(root.findall(f".//{ns['tei_ns']}div"))
    for dix, div in enumerate(divs):
        for eix, elem in enumerate(div):
            if elem.tag == f"{ns['tei_ns']}pb":
                positions.append((dix, eix))
    return positions

def pathize_protocol_id(protocol_id):
    """
    Convert a protocol ID to its corresponding XML file path in `data/`.
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
    if os.path.exists(path_):
        return path_
    path_ = re.sub(r'((extra)?h[^-]+st|")', '', path_)
    if os.path.exists(path_):
        return path_
    raise FileNotFoundError(f"Can't find {path_}")


def unformat_text(text):
    """Clean text by stripping whitespace and joining lines."""
    if text is None:
        return ""
    parts = [p.strip() for p in str(text).splitlines() if p.strip()]
    return " ".join(parts)


def get_text_from_elem(e, acc, ns):
    """Extract text from TEI element `e` recursively, preserving relevant tags."""
    if e is None:
        return
    
    tag = e.tag.split("}", 1)[-1] if "}" in e.tag else e.tag
    if tag in ("note", "p", "fw", "u", "div", "list", "item"):
        txt = unformat_text(e.text)
        if txt:
            acc.append(txt)
        for child in e:
            get_text_from_elem(child, acc, ns)
    else:
        acc.extend([unformat_text(s) for s in e.itertext()])



def get_text_range(path_or_id, pb_range):
    """Extract contiguous text between two <pb> positions as a string."""
    root, ns = cached_parse_tei(path_or_id)
    divs = list(root.findall(f".//{ns['tei_ns']}div"))
    (start_div, start_elem), (end_div, end_elem) = pb_range

    parts = []
    for dix in range(start_div, end_div + 1):
        div = divs[dix]
        if dix == start_div:
            elems = range(start_elem, len(div))
        elif dix == end_div:
            elems = range(0, end_elem + 1 if end_elem is not None else len(div))
        else:
            elems = range(len(div))
        for idx in elems:
            get_text_from_elem(div[idx], parts, ns)

    return "\n".join(parts)


def get_all_text(path_or_id, split_lines):
    """Extract all text from TEI XML according to current structure."""
    root, ns = cached_parse_tei(path_or_id)
    acc = []

    for tag, elem in elem_iter(root):
        get_text_from_elem(elem, acc, ns)

    if split_lines:
        lines = []
        for block in acc:
            for line in block.splitlines():
                line = line.strip()
                if line:
                    lines.append(line)
        return lines
    return "\n".join(acc)


def normalize_text(s, _re_space=re.compile(r"\s+")):
    """Normalize text by removing extra spaces and normalizing dashes; case is preserved."""
    if s is None:
        return ""
    s = str(s)
    s = s.replace('–', '-').replace('—', '-')
    s = _re_space.sub(' ', s).strip()
    return s


def tokenize_by_whitespace(text):
    """Split text into tokens by whitespace."""
    text = normalize_text(text)
    if not text:
        return []
    return [t for t in re.split(r"\s+", text) if t]


def get_most_probable_line_rq(annotation, segments):
    """
    Return the segment that best matches the annotation.
    Approach:
      1. Exact substring match first
      2. Word-token sliding window
      3. Character sliding window
    Returns:
        best_match (str), lev_distance (int), method ('substring', 'token', 'char')
    """
    ann = normalize_text(annotation)
    if not ann:
        return "", 0, "none"

    seg_text = " ".join([normalize_text(s) for s in segments])

    # --- 1. Exact substring check ---
    if ann in seg_text:
        return ann, 0, "substring"

    # --- 2. Token-based sliding window ---
    ann_tokens = tokenize_by_whitespace(ann)
    seg_tokens = []
    for seg in segments:
        seg_tokens.extend(tokenize_by_whitespace(seg))

    best_dist_token = float("inf")
    best_match_token = ""
    if ann_tokens and seg_tokens:
        n = len(ann_tokens)
        for i in range(len(seg_tokens) - n + 1):
            candidate = " ".join(seg_tokens[i:i+n])
            dist = Levenshtein.distance(ann, candidate)
            if dist < best_dist_token:
                best_dist_token = dist
                best_match_token = candidate

    # --- 3. Character sliding window ---
    ann_len = len(ann)
    best_dist_char = float("inf")
    best_match_char = ""
    if ann_len > 0 and len(seg_text) >= ann_len:
        for i in range(0, len(seg_text) - ann_len + 1):
            candidate = seg_text[i:i+ann_len+2]
            dist = Levenshtein.distance(ann, candidate)
            if dist < best_dist_char:
                best_dist_char = dist
                best_match_char = candidate

    if best_dist_token <= best_dist_char:
        return best_match_token, best_dist_token, "token"
    else:
        return best_match_char, best_dist_char, "char"


def process_row_series(row):
    """Process a single annotated row. Returns (most_probable_line, lev_distance, method)."""
    protocol_id = row['protocol_id']
    pb_positions = get_pb_positions(protocol_id)

    if 'facs' in row.index and pd.notna(row.get('x')):
        try:
            page_num = int(row['x'])
        except Exception:
            page_num = None
        if page_num is None or len(pb_positions) == 0:
            segments = get_all_text(protocol_id, split_lines=True)
        else:
            if page_num >= len(pb_positions) - 1:
                start_pb = pb_positions[-2] if len(pb_positions) >= 2 else pb_positions[0]
                end_pb = pb_positions[-1]
            else:
                start_pb = pb_positions[page_num]
                end_pb = pb_positions[page_num + 1]
            segments = get_text_range(protocol_id, (start_pb, end_pb)).splitlines()
    else:
        segments = get_all_text(protocol_id, split_lines=True)

    mp, lev, method = get_most_probable_line_rq(row.get('content', ''), segments)
    return mp, lev, method


def process_csv(sample):
    """Read annotated CSV, process rows, and return dataframe with new columns."""
    df = pd.read_csv(sample, sep=';', encoding='utf-8')
    df['protocol_id'] = df['protocol_id'].apply(pathize_protocol_id)
    out = df.apply(lambda r: process_row_series(r), axis=1)
    df[['most_probable_line', 'lev', 'method']] = pd.DataFrame(out.tolist(), index=df.index)
    df["lev"] = pd.to_numeric(df["lev"])
    return df


def extract_year(path: str):
    m = re.search(r'(18|19|20)\d{2}', path)
    return int(m.group(0)) if m else 0


class OCRQualityEstimator:
    """Handles aggregation, plotting, saving, and resource cleanup for OCR metrics."""
    def __init__(self, estimate_path: str, version: str, show: bool = False, use_pool: bool = False, num_processes: int = 4):
        self.estimate_path = estimate_path
        self.version = version
        self.show = show
        self.pool = Pool(num_processes) if use_pool else None
        self.figures = []
        self.estimate_path = estimate_path
        self.version = version
        self.show = show
        self.fig = None
        self.pool = None
        self.figures = []

    def aggregate_per_year(self, df):
        """Aggregate Levenshtein, WER, CER metrics per year with quantiles, incl. method stats."""
        df = df.copy()

        df['year'] = df['protocol_id'].apply(extract_year)

        def wer_levenshtein(ref: str, hyp: str) -> float:
            """Compute WER = token-level Levenshtein / reference length."""
            ref_tokens = tokenize_by_whitespace(ref)
            hyp_tokens = tokenize_by_whitespace(hyp)
            if not ref_tokens:
                return 1.0 if hyp_tokens else 0.0
            return Levenshtein.distance(ref_tokens, hyp_tokens) / len(ref_tokens)

        df['wer'] = [wer_levenshtein(a, m) for a, m in zip(df['content'], df['most_probable_line'])]
        df['cer'] = [
            Levenshtein.distance(str(a), str(m)) / max(len(str(a)), 1)
            for a, m in zip(df['content'], df['most_probable_line'])
        ]

        df['perfect_match'] = (df['lev'] == 0).astype(int)

        def method_ratio(series, method_name: str):
            return (series == method_name).sum() / len(series) if len(series) > 0 else 0.0

        agg = df.groupby('year').agg(
            lev_mean=('lev', 'mean'),
            lev_first_q=('lev', lambda x: x.quantile(0.25)),
            lev_third_q=('lev', lambda x: x.quantile(0.75)),
            wer_mean=('wer', 'mean'),
            wer_first_q=('wer', lambda x: x.quantile(0.25)),
            wer_third_q=('wer', lambda x: x.quantile(0.75)),
            cer_mean=('cer', 'mean'),
            cer_first_q=('cer', lambda x: x.quantile(0.25)),
            cer_third_q=('cer', lambda x: x.quantile(0.75)),
            perfect_match=('lev', lambda x: (x == 0).sum() / len(x)),
            token_ratio=('method', lambda x: method_ratio(x, "token")),
            char_ratio=('method', lambda x: method_ratio(x, "char"))
        ).reset_index()

        agg.insert(0, 'version', self.version)
        return agg


    def save_metrics(self, df: pd.DataFrame):
        metrics_path = Path(self.estimate_path) / "metrics.csv"
        
        if os.path.exists(metrics_path):
            existing = pd.read_csv(metrics_path)

            if self.version == "v99.99.99":
                existing = existing[existing['version'] != "v99.99.99"]
                combined = pd.concat([existing, df], ignore_index=True)
            elif self.version in existing['version'].unique():
                print(f"Version {self.version} already exists in {metrics_path}, skipping append.")
                combined = existing
            else:
                combined = pd.concat([existing, df], ignore_index=True)
        else:
            combined = df

        combined.to_csv(metrics_path, index=False)
        print(f"Saved combined versioned metrics to {metrics_path}")
        return combined



    def plot_versions(self, df, output_path, y_col = 'cer_mean', n_versions = 6):
        """Plot a metric per year across multiple versions"""
        self.fig = plt.figure(figsize=(12, 6))
        df = df.copy()
        df["version"] = df["version"].astype(str).str.strip()


        versions_sorted = sorted(set(df['version']), key=lambda s: version.parse(s.lstrip('v')), reverse=True)
        colors = list("bgrcmyk")

        for i, v in enumerate(versions_sorted):
            dfv = df[df["version"] == v].sort_values("year")
            plt.plot(dfv["year"], dfv[y_col], label=v, color=colors[i % len(colors)], linewidth=1.75)

        plt.xlabel("Year")
        plt.ylabel(y_col.upper())
        plt.title(f"{y_col.upper()} per year across versions")
        plt.legend()
        plt.tight_layout()

        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        plt.savefig(output_path)
        self.figures.append(self.fig)

        if self.show and self.fig is not None:
            self.fig.show()

    def teardown(self):
        """Release resources by closing figures, pools, and clearing caches."""
        for fig in self.figures:
            plt.close(fig)
        if self.pool:
            self.pool.close()
            self.pool.join()
            self.pool = None
        cached_parse_tei.cache_clear()
        get_pb_positions.cache_clear()
        print("Resources cleaned up.")


def main(args):
    os.makedirs(args.estimate_path, exist_ok=True)
    estimator = OCRQualityEstimator(
        estimate_path=args.estimate_path,
        version=args.version,
        show=args.show,
        use_pool=args.use_pool,
        num_processes=args.num_processes
    )

    mpl_df = None
    if not args.read_lev:
        if args.decade is not None:
            samples = glob(f"{args.annotated_data}/sample_{args.decade}_annotated.csv")
        else:
            samples = glob(f"{args.annotated_data}/*.csv")

        if estimator.pool:
            all_dfs = list(tqdm(estimator.pool.imap_unordered(process_csv, samples),
                                total=len(samples), desc="All CSVs"))
        else:
            all_dfs = [process_csv(s) for s in tqdm(samples, desc="All CSVs")]
        if all_dfs:
            mpl_df = pd.concat(all_dfs, ignore_index=True)

    if mpl_df is None:
        return

    df_year = estimator.aggregate_per_year(mpl_df)
    combined = estimator.save_metrics(df_year)

    estimator.plot_versions(combined, os.path.join(args.estimate_path, "cer_versions.png"), y_col='cer_mean')
    estimator.plot_versions(combined, os.path.join(args.estimate_path, "wer_versions.png"), y_col='wer_mean')
    estimator.plot_versions(combined, os.path.join(args.estimate_path, "lev_versions.png"), y_col='lev_mean')

    estimator.teardown()


if __name__ == '__main__':
    parser = fetch_parser("records", docstring=__doc__)
    parser.add_argument("-d", "--annotated-data",
                        type=str,
                        default="quality/data/ocr-estimation",
                        help="Path to annotated OCR quality-control data")
    parser.add_argument("-D", "--decade",
                        type=str,
                        default=None,
                        help="Calculate metrics for a single decade")
    parser.add_argument("-o", "--estimate-path",
                        type=str,
                        default="quality/estimates/ocr-estimation",
                        help="Path where the current estimate will be written")
    parser.add_argument("--read-lev",
                        action='store_true',
                        help="Read most probable line and Levenshtein distance from a file")
    parser.add_argument("--lev-only",
                        action='store_true',
                        help="Only calculate Levenshtein distances")
    parser.add_argument("--concat-lev",
                        action='store_true',
                        help="Save concatenated Levenshtein distances")
    parser.add_argument("--skip-second-search",
                        type=bool,
                        default=True,
                        help="Skip looking for line again when Levenshtein > lev-threshold")
    parser.add_argument("--no-skip-second-search",
                        dest="skip_second_search",
                        action="store_false",
                        help="Do not skip second search")
    parser.add_argument("--ignore-dash",
                        action='store_true',
                        help="Recalculate deviation without line-final dash")
    parser.add_argument("--lev-threshold",
                        type=float,
                        default=2.0,
                        help="Threshold for triggering second search on Levenshtein distance")
    parser.add_argument("-v", "--version",
                        type=str,
                        default="v99.99.99",
                        help="Version string for this run (semantic versioning)")
    parser.add_argument("--show",
                        action="store_true",
                        help="Display plots interactively (disabled by default for CI)")
    parser.add_argument("--use-pool", 
                        action="store_true", 
                        help="Process CSVs using multiprocessing Pool")
    parser.add_argument("--num-processes", 
                        type=int, 
                        default=max(1, cpu_count() - 1),
                        help="Number of processes to use if --use-pool is enabled")
    args = impute_args(parser.parse_args())
    main(args)