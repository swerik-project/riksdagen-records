#!/usr/bin/env python3
"""
Check that gold-standard speaker annotations have NOT been changed
by later processing of protocol XML files.
Logic:
- Read gold-standard TSVs (is-speaker / non-speaker)
- For each row, locate the element by xml:id in the protocol file
- Verify that:
* is-speaker: element still has the expected concrete @who / speaker type
* non-speaker: element is still non-speaker (no @who, no type="speaker")
"""

import argparse
from glob import glob
import os
from multiprocessing import Pool, cpu_count
import pandas as pd
from pyriksdagen.io import parse_tei
from tqdm import tqdm
from trainerlog import get_logger
import unittest
import sys

logger = get_logger(name="goldstandard_drift_test", level="INFO")

TEI_NS = "http://www.tei-c.org/ns/1.0"
XML_NS = "http://www.w3.org/XML/1998/namespace"


def find_element_by_xml_id(root, uuid):
    if not uuid:
        return None
    ns = {
        'xml': XML_NS,
        'tei': TEI_NS,
    }
    res = root.xpath(f".//*[@xml:id='{uuid}']", namespaces=ns)
    return res[0] if res else None


def process_row(r):
    xml_path = r['protocol_id']
    uuid = r['uuid']
    folder_type = r['folder_type']
    expected_person = r['person_id']

    result = {'not_found': None, 'fail_is_speaker': None, 'fail_non_speaker': None}

    if not xml_path or not os.path.exists(xml_path):
        result['not_found'] = [xml_path, uuid, "file not found"]
        logger.error(f"File not found: {xml_path}")
        return result

    root, ns = parse_tei(xml_path)
    el = find_element_by_xml_id(root, uuid)

    if el is None:
        result['not_found'] = [xml_path, uuid, "uuid not found"]
        logger.error(f"UUID not found: {uuid} in {xml_path}")
        return result

    if folder_type == 'is-speaker':
        if el.tag.endswith('u') and el.get('who') != expected_person:
            result['fail_is_speaker'] = [xml_path, uuid, expected_person, el.get('who')]
            logger.error(f"Speaker drift: {uuid} expected {expected_person}, got {el.get('who')}")
        if el.tag.endswith('note') and el.get('type') != 'speaker':
            result['fail_is_speaker'] = [xml_path, uuid, 'type=speaker', el.get('type')]
            logger.error(f"Speaker note drift: {uuid}")
    else:
        if el.get('who') or (el.tag.endswith('note') and el.get('type') == 'speaker'):
            actual = el.get('who') if el.get('who') else 'type=speaker'
            result['fail_non_speaker'] = [xml_path, uuid, actual]
            logger.error(f"Non-speaker drift: {uuid} ({actual})")

    return result


class GoldStandardDriftTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        super(GoldStandardDriftTests, cls).setUpClass()

        cls.base_folder = "test/data/speaker-segments"
        cls.fail_is_speaker = []
        cls.fail_non_speaker = []
        cls.not_found = []
        cls.rows = []

        for folder in ["is-speaker", "non-speaker"]:
            folder_path = os.path.join(cls.base_folder, folder)
            for tsv in glob(os.path.join(folder_path, "*.tsv")):
                df = pd.read_csv(tsv, sep="\t", dtype=str).fillna('')
                for idx, row in df.iterrows():
                    cls.rows.append({
                        'folder_type': folder,
                        'protocol_id': row.get('protocol_id'),
                        'uuid': row.get('uuid'),
                        'person_id': row.get('person_id'),
                        'row_index': idx,
                        'source': tsv,
                    })

    @classmethod
    def tearDownClass(cls):
        print("\nMissing UUIDs:", cls.not_found[:5], "\n", len(cls.not_found), "instances")
        print("\nGold is-speaker drift:", cls.fail_is_speaker[:5], "\n", len(cls.fail_is_speaker), "instances")
        print("\nGold non-speaker drift:", cls.fail_non_speaker[:5], "\n", len(cls.fail_non_speaker), "instances")

        if cls.not_found:
            pd.DataFrame(cls.not_found, columns=["file", "uuid", "problem"]).to_csv(
                "test/results/gold-uuid-not-found.tsv", sep="\t", index=False
            )

        if cls.fail_is_speaker:
            pd.DataFrame(cls.fail_is_speaker, columns=["file", "uuid", "expected", "actual"]).to_csv(
                "test/results/gold-is-speaker-drift.tsv", sep="\t", index=False
            )

        if cls.fail_non_speaker:
            pd.DataFrame(cls.fail_non_speaker, columns=["file", "uuid", "actual"]).to_csv(
                "test/results/gold-non-speaker-drift.tsv", sep="\t", index=False
            )

    def test_goldstandard_not_overwritten(self):
        """Verify that gold-standard speaker decisions still hold in XML."""

        use_mp = getattr(self, 'use_multiprocess', False)

        if use_mp:
            n_workers = min(cpu_count(), len(self.rows))
            with Pool(n_workers) as pool:
                results = list(tqdm(pool.imap_unordered(process_row, self.rows), total=len(self.rows)))
        else:
            results = [process_row(r) for r in tqdm(self.rows)]

        for res in results:
            if res['not_found']:
                self.not_found.append(res['not_found'])
            if res['fail_is_speaker']:
                self.fail_is_speaker.append(res['fail_is_speaker'])
            if res['fail_non_speaker']:
                self.fail_non_speaker.append(res['fail_non_speaker'])

        self.assertEqual(0, len(self.not_found), "Some gold UUIDs are missing")
        self.assertEqual(0, len(self.fail_is_speaker), "Some gold speakers were overwritten")
        self.assertEqual(0, len(self.fail_non_speaker), "Some gold non-speakers were overwritten")


if __name__ == '__main__':

    parser = argparse.ArgumentParser(description="Gold-standard speaker drift tests")
    parser.add_argument(
        "--base-folder",
        default="test/data/speaker-segments",
        help="Base folder containing is-speaker / non-speaker TSVs"
    )
    parser.add_argument(
        "--loglevel",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Logger level (default: INFO)"
    )
    parser.add_argument(
        "--multiprocess",
        action="store_true",
        help="Parse XML files in parallel (read-only)"
    )

    args, remaining = parser.parse_known_args()

    logger.setLevel(args.loglevel)
    GoldStandardDriftTests.base_folder = args.base_folder
    GoldStandardDriftTests.use_multiprocess = args.multiprocess

    sys.argv = [sys.argv[0]] + remaining
    unittest.main()
