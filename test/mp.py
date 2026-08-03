"""
Test suite for validating Swedish parliamentary protocol data.

Checks:
- MPs appearing in protocols outside their mandate periods
- MPs appearing in protocols after death
- MPs appearing in protocols before age 15

Uses baseline CSV files to compare error counts via confidence intervals (CI).
Logs results using trainerlog.
"""

from datetime import datetime
from pathlib import Path
from pyriksdagen.db import load_metadata
from pyriksdagen.io import parse_tei
from pyriksdagen.utils import get_doc_dates
from trainerlog import get_logger

import calendar
import math
import os
import pandas as pd
import progressbar
import unittest

logger = get_logger(name="mp-test")

def parse_date_start(s):
    """Parse a string into a start datetime. Returns 1800-01-01 if missing."""

    if pd.isna(s) or str(s).strip() == "":
        return datetime(1800, 1, 1)
    try:
        dt = pd.to_datetime(s, errors="coerce")
        if pd.notna(dt):
            return dt
        parts = str(s).split("-")
        year = int(parts[0])
        month = int(parts[1]) if len(parts) > 1 else 1
        day = int(parts[2]) if len(parts) > 2 else 1
        return datetime(year, month, day)
    except:
        return None


def parse_date_end(s):
    """Parse a string into an end datetime. Returns max datetime if missing."""
    if pd.isna(s) or str(s).strip() == "" or str(s).strip() == "NaT":
        return pd.Timestamp.max.to_pydatetime()
    try:
        dt = pd.to_datetime(s, errors="coerce")
        if pd.notna(dt):
            return dt
        parts = str(s).split("-")
        year = int(parts[0])
        month = int(parts[1]) if len(parts) > 1 else 12
        day = int(parts[2]) if len(parts) > 2 else calendar.monthrange(year, month)[1]
        return datetime(year, month, day)
    except:
        return None
    

def assert_ci(baseline_file, new_df, confidence=0.95):
    """
    Compare the number of errors in a DataFrame against a baseline CSV using a confidence interval.
    Logs info, warnings, or errors and raises AssertionError if outside CI.
    """
    df = pd.read_csv(baseline_file)
    
    ci_low = len(df) - 2*math.sqrt(len(df))
    ci_high = len(df) + 2*math.sqrt(len(df))

    new_count = len(new_df)

    logger.info(f"Baseline error count: {len(df)}")
    logger.info(f"Allowed error count within {int(confidence*100)}% CI: [{ci_low:.0f}, {ci_high:.0f}]")
    logger.info(f"New error count: {new_count}")

    if ci_low <= new_count <= ci_high:
        status = "inside"
    elif new_count > ci_high:
        status = "above"
    else:
        status = "below"

    if status == "inside":
        mid_ci = ci_low + (ci_high - ci_low)/2
        if new_count > mid_ci:
            logger.warning(f"Error count {new_count} increased but remains within CI [{ci_low:.0f}, {ci_high:.0f}].")
        elif new_count == mid_ci:
            logger.info(f"Error count {new_count} is at midpoint of CI; no change detected.")
        else:
            logger.warning(f"Error count {new_count} decreased but remains within CI [{ci_low:.0f}, {ci_high:.0f}].")
    elif status == "above":
        logger.error(f"Error count {new_count} exceeds upper CI bound [{ci_low:.0f}, {ci_high:.0f}]!")
        raise AssertionError(f"Error count {new_count} exceeds upper CI bound [{ci_low:.0f}, {ci_high:.0f}]!")
    else:
        logger.error(f"Error count {new_count} falls below lower CI bound [{ci_low:.0f}, {ci_high:.0f}]!")
        raise AssertionError(f"Error count {new_count} falls below lower CI bound [{ci_low:.0f}, {ci_high:.0f}]!")


def aggregate_dates(df_subset):
    """
    Aggregate protocol dates, birth, death, and speaker info for each protocol-person combination.
    Returns a DataFrame with combined information.
    """
    return (
        df_subset.groupby(["protocol_id","person_id"])
        .agg(
            protocol_dates=("protocol_date",
                lambda x: ";".join(sorted(x.dt.strftime("%Y-%m-%d").unique()))
            ),
            born=("born","first"),
            dead=("dead","first"),
            speaker_intro_text=("speaker_intro_text","first")
        )
        .reset_index()
    )


def append_raw_open_ended_intervals(mp_db):
    """Temporary workaround for pyriksdagen truncating open-ended intervals.

    Remove this once pyriksdagen preserves blank end dates for current
    MP/minister/speaker rows in load_metadata().
    """
    metadata_path = os.environ.get("METADATA_PATH")
    if not metadata_path:
        return mp_db

    demographics = mp_db[["id", "born", "dead"]].drop_duplicates(subset=["id"])
    raw_rows = []

    for filename, source in [
        ("member_of_parliament.csv", "member_of_parliament"),
        ("minister.csv", "minister"),
        ("speaker.csv", "speaker"),
    ]:
        source_path = Path(metadata_path) / filename
        if not source_path.exists():
            continue

        raw = pd.read_csv(source_path, dtype=str)
        raw = raw[
            raw["start"].notna()
            & raw["start"].str.strip().ne("")
            & (raw["end"].isna() | raw["end"].str.strip().eq(""))
        ].copy()

        if raw.empty:
            continue

        raw = raw.rename(columns={"person_id": "id"})
        raw["source"] = source
        raw = raw.merge(demographics, on="id", how="left")

        for column in mp_db.columns:
            if column not in raw.columns:
                raw[column] = pd.NA

        raw_rows.append(raw[mp_db.columns])

    if not raw_rows:
        return mp_db

    return pd.concat([mp_db, *raw_rows], ignore_index=True)

class Test(unittest.TestCase):

    def test_protocol(self):

        folder = "data"
        *_, mp_db, minister_db, speaker_db = load_metadata()

        mp_db = pd.concat([mp_db, minister_db, speaker_db])
        mp_db = append_raw_open_ended_intervals(mp_db)
        mp_db["start"] = mp_db["start"].map(parse_date_start)
        mp_db["end"] = mp_db["end"].map(parse_date_end)

        mp_doa = mp_db[["id", "born", "dead"]].drop_duplicates().reset_index(drop=True)
        mp_doa["born"] = pd.to_datetime(mp_doa["born"], errors="coerce")
        mp_doa["dead"] = pd.to_datetime(mp_doa["dead"], errors="coerce")
        mp_doa = mp_doa.rename(columns={"id": "person_id"})

        records = []

        # Find the dates, people and intros in protocols
        for outfolder in progressbar.progressbar(list(Path(folder).glob("*/"))):
            for protocol_path in outfolder.glob("*.xml"):

                protocol_id = protocol_path.stem
                root, ns = parse_tei(str(protocol_path))

                match_error, dates = get_doc_dates(root)
                protocol_dates = [pd.to_datetime(d, errors="coerce") for d in dates if d]

                if not protocol_dates:
                    continue

                last_speaker_intro = ""

                for body in root.findall(f".//{ns['tei_ns']}body"):
                    for div in body.findall(f"{ns['tei_ns']}div"):
                        for elem in div:

                            if (
                                elem.tag == f"{ns['tei_ns']}note"
                                and elem.attrib.get("type") == "speaker"
                            ):
                                if elem.text:
                                    last_speaker_intro = elem.text.strip()

                            elif elem.tag == f"{ns['tei_ns']}u":

                                who = elem.attrib.get("who")

                                if not who or who == "unknown":
                                    continue

                                for pdate in protocol_dates:
                                    records.append({"protocol_id": protocol_id, "person_id": who, "protocol_date": pdate, "speaker_intro_text": last_speaker_intro})

        df = pd.DataFrame(records)

        relevant_ids = df["person_id"].unique()
        mp_subset = mp_db[mp_db["id"].isin(relevant_ids)][["id", "start", "end"]]

        df_merged = df.merge(mp_subset, how="left", left_on="person_id", right_on="id")
        df_merged["valid_mandate"] = ((df_merged["protocol_date"] >= df_merged["start"]) & (df_merged["protocol_date"] <= df_merged["end"]))

        # For each protocol/person, check if ANY protocol_date matches a mandate
        mandate_check = (df_merged.groupby(["protocol_id","person_id"])["valid_mandate"].any().reset_index())

        df_fail = mandate_check[~mandate_check["valid_mandate"]].drop(columns="valid_mandate")

        df_fail_dates = (
            df.groupby(["protocol_id", "person_id"])["protocol_date"]
            .apply(
                lambda x: ";".join(
                    sorted(x.dt.strftime("%Y-%m-%d").unique())
                )
            )
            .reset_index(name="protocol_dates")
        )

        df_fail = df_fail.merge(df_fail_dates, on=["protocol_id", "person_id"])

        df_intro = df[["protocol_id", "person_id", "speaker_intro_text"]].drop_duplicates()

        df_fail = df_fail.merge(df_intro, on=["protocol_id", "person_id"], how="left")

        # Child-dead checks
        df = df.merge(mp_doa, on="person_id", how="left")

        df_dead = df[(df["dead"].notna()) & (df["protocol_date"] > df["dead"])].copy()
        df_child = df[(df["born"].notna()) & (df["protocol_date"] < df["born"] + pd.DateOffset(years=15))].copy()

        df_dead = aggregate_dates(df_dead)
        df_child = aggregate_dates(df_child)

        df_fail  = df_fail.drop_duplicates(subset=["protocol_id","person_id"])
        df_dead  = df_dead.drop_duplicates(subset=["protocol_id","person_id"])
        df_child = df_child.drop_duplicates(subset=["protocol_id","person_id"])

        # Write results
        results_dir = "test/results"
        os.makedirs(results_dir, exist_ok=True)

        df_fail.to_csv(f"{results_dir}/missing-persons.csv", index=False)
        df_dead.to_csv(f"{results_dir}/dead-mps.csv", index=False)
        df_child.to_csv(f"{results_dir}/child-mps.csv", index=False)

        # Check changes
        failures = []

        baseline_dir = "test/data/mp"

        try:
            logger.info(f"=== Checking {len(df_fail)} errors for MP presence in protocol vs MP mandate periods ===")
            assert_ci(f"{baseline_dir}/baseline-missing-persons.csv", df_fail)
            logger.info("")
        except AssertionError as e:
            failures.append(str(e))

        try:
            logger.info(f"=== Checking {len(df_dead)} errors for MPs appearing in protocol after death ===")
            assert_ci(f"{baseline_dir}/baseline-dead-mps.csv", df_dead)
            logger.info("")
        except AssertionError as e:
            failures.append(str(e))

        try:
            logger.info(f"=== Checking {len(df_child)} errors for MPs appearing in protocol before age 15 ===")
            assert_ci(f"{baseline_dir}/baseline-child-mps.csv", df_child)
        except AssertionError as e:
            failures.append(str(e))

        if failures:
            raise AssertionError("\n".join(failures))


if __name__ == "__main__":
    unittest.main()
