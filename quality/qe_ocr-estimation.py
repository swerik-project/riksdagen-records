#!/usr/bin/env python3
"""
OCR Quality Estimation Script

This script evaluates the quality of OCRed text against annotated reference text.
It computes metrics such as:
- Levenshtein distance (LEV)
- Word Error Rate (WER)
- Character Error Rate (CER)
- Perfect match ratio (percentage of exact matches)

The script processes TEI XML protocols, aligns annotated lines with OCR segments,
aggregates metrics per year, and saves the results to a versioned CSV.
It also generates plots for CER, WER, and LEV over years across multiple versions.
"""
from functools import lru_cache
from glob import glob
from multiprocessing import (
    cpu_count,
    Pool
)
from pathlib import Path
import os
import re
from typing import (
    List, 
    Optional, 
    Tuple,
    Union
)
import matplotlib.pyplot as plt
import pandas as pd
from pyriksdagen.args import (
    fetch_parser, 
    impute_args
)
from pyriksdagen.io import parse_tei
from pyriksdagen.utils import elem_iter
from rapidfuzz.distance import Levenshtein
from tqdm import tqdm

def pathize_protocol_id(protocol_id: str) -> str:
    """Resolve a protocol identifier into a file path.
    Returns a string path if found, raises FileNotFoundError otherwise.
    """
    parts = protocol_id.split("-")
    try:
        py = parts[1]
    except IndexError:
        raise FileNotFoundError(f"Malformed protocol id: {protocol_id}")

    suffix = ""
    if len(parts) == 4:
        nr = parts[3]
        pren = "-".join(parts[:3])
    else:
        nr = parts[5]
        pren = "-".join(parts[:5])
        if len(parts) == 7:
            suffix = f"-{parts[-1]}"

    candidate = Path(f"data/{py}/{pren}-{nr:0>3}{suffix}.xml")
    if candidate.exists():
        return str(candidate)

    # fallback sanitisation used in original code
    sanitized = re.sub(r'((extra)?h[^-]+st|")', '', str(candidate))
    candidate2 = Path(sanitized)
    if candidate2.exists():
        return str(candidate2)

    raise FileNotFoundError(f"Can't find {protocol_id} -> {candidate}")


@lru_cache(maxsize=256)
def cached_parse_tei(path_or_id: str):
    """Parse TEI XML and cache result per process. Returns (root, ns)."""
    return parse_tei(path_or_id)


@lru_cache(maxsize=256)
def get_pb_positions(path_or_id: str) -> List[Tuple[int, int]]:
    """Return cached list of (div_index, elem_index) positions of <pb> tags."""
    root, ns = cached_parse_tei(path_or_id)
    positions = []
    divs = list(root.findall(f".//{ns['tei_ns']}div"))
    for dix, div in enumerate(divs):
        for eix, elem in enumerate(div):
            if elem.tag == f"{ns['tei_ns']}pb":
                positions.append((dix, eix))
    return positions


def unformat_text(text: Optional[str]) -> str:
    if text is None:
        return ""
    parts = [p.strip() for p in str(text).splitlines() if p.strip()]
    return " ".join(parts)


def get_text_from_elem(e, acc: List[str], ns) -> None:
    """Append normalized text from element `e` into list `acc` (in place)."""
    if e is None:
        return
    tag = e.tag
    if tag == f"{ns['tei_ns']}note":
        txt = unformat_text(e.text)
        if txt:
            acc.append(txt)
    elif tag == f"{ns['tei_ns']}u":
        for seg in e:
            txt = unformat_text(getattr(seg, 'text', None))
            if txt:
                acc.append(txt)
    else:
        txt = unformat_text("".join(e.itertext()))
        if txt:
            acc.append(txt)


def get_text_range(path_or_id: str, pb_range: Tuple[Tuple[int, int], Tuple[int, int]]) -> str:
    """Extract contiguous text between two <pb> positions as a string."""
    root, ns = cached_parse_tei(path_or_id)
    divs = list(root.findall(f".//{ns['tei_ns']}div"))
    (start_div, start_elem), (end_div, end_elem) = pb_range

    parts: List[str] = []
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


def get_all_text(path_or_id: str, split_lines: bool = False) -> Union[List[str], str]:
    root, ns = cached_parse_tei(path_or_id)
    acc: List[str] = []
    for tag, elem in elem_iter(root):
        get_text_from_elem(elem, acc, ns)
    if split_lines:
        return [p for p in acc if p]
    return "\n".join(acc)


def normalize_text(s: Optional[str], _re_space=re.compile(r"\s+")) -> str:
    if s is None:
        return ""
    s = str(s).lower()
    s = s.replace('–', '-').replace('—', '-')
    s = _re_space.sub(' ', s).strip()
    return s

def sliding_windows(text: str, window_len: int) -> List[str]:
    n = len(text)
    if n <= window_len:
        return [text]
    return [text[i:i+window_len] for i in range(n - window_len + 1)]


def get_most_probable_line_rq(annotation: str, segments: List[str], min_window: int = 20) -> Tuple[str, int]:
    """Return substring from `segments` with minimal Levenshtein distance to `annotation`."""
    ann = normalize_text(annotation)
    best_lev = float('inf')
    best_text = ""
    ann_len = len(ann)
    window_len = max(ann_len, min_window)

    for seg in segments:
        seg_norm = normalize_text(seg)
        seg_len = len(seg_norm)
        if seg_len == 0:
            continue
        if seg_len <= window_len:
            lev = Levenshtein.distance(ann, seg_norm)
            if lev < best_lev:
                best_lev = lev
                best_text = seg_norm
        else:
            for w in sliding_windows(seg_norm, window_len):
                lev = Levenshtein.distance(ann, w)
                if lev < best_lev:
                    best_lev = lev
                    best_text = w
    return best_text, int(best_lev if best_lev != float('inf') else 0)


def process_row_series(row: pd.Series) -> Tuple[str, int]:
    """Process a single annotated row. Returns (most_probable_line, lev_distance)."""
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

    mp, lev = get_most_probable_line_rq(row.get('content', ''), segments)
    return mp, lev


def process_csv(sample: str) -> pd.DataFrame:
    """Read annotated CSV, process rows, and return dataframe with new columns."""
    df = pd.read_csv(sample, sep=';', encoding='utf-8')
    df['protocol_id'] = df['protocol_id'].apply(pathize_protocol_id)

    out = df.apply(lambda r: process_row_series(r), axis=1)
    df[['most_probable_line', 'lev']] = pd.DataFrame(out.tolist(), index=df.index)

    return df


class OCRQualityEstimator:
    def __init__(self, estimate_path: str, version: str, show: bool = False):
        self.estimate_path = estimate_path
        self.version = version
        self.show = show
        self.fig = None
        self.pool = None
        self.figures = []

    @staticmethod
    def version_key(v: str) -> List[int]:
        """Convert semantic version string to integer list for sorting."""
        if v == "v99.99.99":
            return [999, 999, 999]
        if not v.startswith("v"):
            v = "v" + v
        parts = v[1:].split(".")
        if len(parts) != 3:
            raise ValueError(f"Invalid version string: {v!r} (must be 'vX.Y.Z')")
        try:
            return [int(p) for p in parts]
        except ValueError:
            raise ValueError(f"Invalid version string: {v!r} (non-integer component)")

    def aggregate_per_year(self, df: pd.DataFrame) -> pd.DataFrame:
        """Aggregate Levenshtein, WER, CER metrics per year with quantiles."""
        df = df.copy()

        def extract_year(path: str):
            m = re.search(r'(18|19|20)\d{2}', path)
            return int(m.group(0)) if m else 0

        df['year'] = df['protocol_id'].apply(extract_year)

        def wer_levenshtein(ref: str, hyp: str) -> float:
            ref_tokens = ref.split()
            hyp_tokens = hyp.split()
            if len(ref_tokens) == 0:
                return 1.0 if len(hyp_tokens) > 0 else 0.0
            lev = Levenshtein.distance(" ".join(ref_tokens), " ".join(hyp_tokens))
            return lev / len(ref_tokens)

        df['wer'] = [wer_levenshtein(a, m) for a, m in zip(df['content'], df['most_probable_line'])]
        ann_len = df['content'].str.len().replace(0, 1).to_numpy()
        df['cer'] = df['lev'].to_numpy() / ann_len

        df['perfect_match'] = (df['lev'] == 0).astype(int)

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
            perfect_match=('lev', lambda x: (x == 0).sum() / len(x))
        ).reset_index()
        agg.insert(0, 'version', self.version)
        return agg

    def save_metrics(self, df: pd.DataFrame):
        metrics_path = Path(self.estimate_path) / "metrics.csv"

        # Flatten column names to avoid MultiIndex issues
        #df.columns = [c if isinstance(c, str) else "_".join(c).strip() for c in df.columns]

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



    def plot_versions(self, df: pd.DataFrame, output_path: str, y_col: str = 'cer_mean', n_versions: int = 6):
        """Plot a metric per year across multiple versions"""
        self.fig = plt.figure(figsize=(12, 6))
        df = df.copy()
        df["version"] = df["version"].astype(str).str.strip()

        # take top n_versions by version number
        versions_sorted = sorted(df["version"].unique(), key=OCRQualityEstimator.version_key, reverse=True)[:n_versions]
        colors = list("bgrcmyk")

        for i, v in enumerate(versions_sorted):
            dfv = df[df["version"] == v].sort_values("year")
            plt.plot(dfv["year"], dfv[y_col], label=v, color=colors[i % len(colors)], linewidth=1.75)

        plt.xlabel("Year")
        plt.ylabel(y_col.upper())
        plt.title(f"{y_col.upper()} per year across versions")
        plt.legend()
        plt.tight_layout()
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
        cached_parse_tei.cache_clear()
        get_pb_positions.cache_clear()
        print("Resources cleaned up.")


def main(args):
    os.makedirs(args.estimate_path, exist_ok=True)
    estimator = OCRQualityEstimator(estimate_path=args.estimate_path, version=args.version, show = args.show)

    mpl_df = None
    if not args.read_lev:
        if args.decade is not None:
            samples = glob(f"{args.annotated_data}/sample_{args.decade}_annotated.csv")
        else:
            samples = glob(f"{args.annotated_data}/*.csv")

        n_workers = max(1, cpu_count() - 1)
        estimator.pool = Pool(n_workers)
        try:
            all_dfs = list(tqdm(estimator.pool.imap_unordered(process_csv, samples), total=len(samples), desc="All CSVs"))
        finally:
            estimator.pool.close()
            estimator.pool.join()

        if len(all_dfs) > 0:
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
    parser.add_argument("-d", "--annotated-data", type=str, default="quality/data/ocr-estimation")
    parser.add_argument("-D", "--decade", type=str, default=None)
    parser.add_argument("-o", "--estimate-path", type=str, default="quality/estimates/ocr-estimation")
    parser.add_argument("--read-lev", action='store_true')
    parser.add_argument("--lev-only", action='store_true')
    parser.add_argument("--concat-lev", action='store_true')
    parser.add_argument("--skip-second-search", action='store_true')
    parser.add_argument("--no-skip-second-search", dest="skip_second_search", action="store_false")
    parser.set_defaults(skip_second_search=True)
    parser.add_argument("--ignore-dash", action='store_true')
    parser.add_argument("--lev-threshold", type=float, default=2.0)
    parser.add_argument(
    "-v", "--version",
    type=str,
    default="v99.99.99",
    help="Version string for this run (semantic versioning)"
    )
    parser.add_argument("--show", type=lambda x: x.lower() in ['true', '1', 'yes'], default=True)
    args = impute_args(parser.parse_args())
    main(args)