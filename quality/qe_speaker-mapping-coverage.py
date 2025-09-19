"""
Estimate and Draw a plot of the introduction mapping coverage.

.. inclide:: dpcs/qe_speaker-mapping-coverage.md
"""
from cycler import cycler
from multiprocessing import Pool
from pyriksdagen.args import (
    fetch_parser,
    impute_args,
)
from pyriksdagen.utils import (
    get_data_location,
    parse_protocol,
    protocol_iterators,
)
from tqdm import tqdm
import argparse
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import re




def update_plot(version):
    """
    Plot coverage against previous versions.
    """
    colors = list('bgrcmyk')
    default_cycler = (cycler(color=colors) +
                      cycler(linestyle=(['-', '--', ':', '-.']*2)[:len(colors)]))
    plt.rc('axes', prop_cycle=default_cycler)
    f, ax = plt.subplots()

    df = pd.read_csv('quality/estimates/speaker-mapping-coverage/difference.csv')
    if args.version != "v99.99.99":
        for c in ["v99.99.99", "v0.0.0"]:
            if c in df.columns:
                df.drop(columns=[c], inplace=True)
    # Overwrite current version
    if len(df[df['version'] == version]) > 1:
        df = df[df['version'] != version]

    # Add current version
    accuracy = pd.read_csv('quality/estimates/speaker-mapping-coverage/upper_bound.csv')
    accuracy = accuracy[['year', 'accuracy_upper_bound']].rename(columns={'accuracy_upper_bound':'accuracy'})
    accuracy['version'] = version
    df = pd.concat([df, accuracy])

    # Save new values
    df.to_csv('quality/estimates/speaker-mapping-coverage/difference.csv', index=False)

    # prepend 'v' to version nr if not already there
    df['version'] = df['version'].apply(lambda s: s if s.startswith('v') else f'v{s}')

    # sort versions
    #    (a) first by patch, then minor, then major and
    #    (b) by int (10, 9 ... 2, 1) not str ('9' ... '2', '10', '1')
    version = sorted(list(set([v for v in df['version'] if "rc" not in v])), key=lambda s: list(map(int, s[1:].split('.'))), reverse=True)

    for v in version[:6]:
        dfv = df.loc[df['version'] == v]
        x = dfv['year'].tolist()
        y = dfv['accuracy'].tolist()
        x, y = zip(*sorted(zip(x,y),key=lambda x: x[0]))
        plt.plot(x, y, linewidth=1.75)

    plt.title('Coverage of identified speakers')
    plt.legend(version, loc ="upper left")
    ax.set_xlabel('Year')
    ax.set_ylabel('Accuracy')
    return f, ax


# Fix parallellization
def accuracy(protocol):
    """
    Count known and unknown in intros
    """
    root, ns = parse_protocol(protocol, get_ns=True)
    for docDate in root.findall(f".//{ns['tei_ns']}docDate"):
        date_string = docDate.text.strip()
        break
    year = int(date_string[:4])
    known, unknown = 0, 0
    for div in root.findall(f".//{ns['tei_ns']}div"):
        for elem in div:
            if "who" in elem.attrib:
                who = elem.attrib["who"]
                if who == "unknown":
                    unknown += 1
                else:
                    known += 1
    return year, known, unknown


def calculate_upper_bound(args):
    """
    Calculate coverage upper bound for each record
    """
    years = sorted(set([int(p.split('/')[-2][:4]) for p in args.records]))
    years.append(max(years)+1)
    df = pd.DataFrame(
                np.zeros((len(years), 2), dtype=int),
                index=years,
                columns=['known', 'unknown'])
    pool = Pool()
    for year, known, unknown in tqdm(pool.imap(accuracy, args.records), total=len(args.records)):
        df.loc[year, 'known'] += known
        df.loc[year, 'unknown'] += unknown
    df['accuracy_upper_bound'] = df.div(df.sum(axis=1), axis=0)['known']
    return df




def main(args):
    print("Calculate Upper Bound...")
    df = calculate_upper_bound(args)
    print(df)
    print(" -- Average:", df['accuracy_upper_bound'].mean())
    print(" -- Weighted average:", df["known"].sum() / (df["known"] + df["unknown"]).sum())
    print(" -- Minimum: {} ({})".format(*[getattr(df['accuracy_upper_bound'], f)() for f in ['min', 'idxmin']]))
    df.to_csv("quality/estimates/speaker-mapping-coverage/upper_bound.csv", index_label='year')


    print("Plotting plot")
    f, ax = update_plot(args.version)
    plt.savefig('quality/estimates/speaker-mapping-coverage/speaker-mapping-coverage.png', dpi=300)
    if args.show:
        plt.show()
        plt.close()




if __name__ == "__main__":
    parser = fetch_parser("records")
    parser.add_argument("-v", "--version", type=str)
    parser.add_argument("--show", type=str, default="True")
    args = parser.parse_args()
    args.show = False if args.show.lower()[:1] == "f" else True
    if args.version:
        exp = re.compile(r"v([0-9]+)([.])([0-9]+)([.])([0-9]+)(b|rc)?([0-9]+)?")
        if exp.search(args.version) is None:
            print(f"{args.version} is not a valid version number. Exiting")
            exit()
        else:
            args.version = exp.search(args.version).group(0)
    else:
        args.version = "v99.99.99"
    main(impute_args(parser.parse_args()))
