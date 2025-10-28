#!/usr/bin/env python3
"""
Test suite for validating non-speaker mapping in TEI XML protocols.

Checks that:
1. Elements expected *not* to be speakers do not have type='speaker'.
2. If a UUID is missing, it attempts to find a candidate match based on text similarity.
3. Caches XML files to avoid reading the same file twice.
4. Optionally supports multiprocessing for faster execution on large corpora.
5. Logs failures to test/output/non_speaker_failures.tsv.
"""
import os
import re
import unittest
import pandas as pd
from lxml import etree
from tqdm import tqdm
from typing import Dict
import argparse
import nltk
from pyriksdagen.io import parse_tei
from multiprocessing import Pool

XML_NS = "http://www.w3.org/XML/1998/namespace"
XML_ID_ATTR = f"{{{XML_NS}}}id"


def normalize_whitespace(s):
    return ' '.join(s.split()) if s else ''


def tokenize_words(s):
    return [w for w in re.findall(r'\w+', (s or '').lower()) if w]


def get_xml_id(elem):
    return elem.get(XML_ID_ATTR) or elem.get("id") or "[NOUUID]"


def flatten_segment_text(elem):
    parts = [elem.text.strip()] if elem.text and elem.text.strip() else []
    for child in elem:
        if child.text and child.text.strip():
            parts.append(child.text.strip())
        if child.tail and child.tail.strip():
            parts.append(child.tail.strip())
    return normalize_whitespace(' '.join(parts))


def find_element_by_xml_id(root, uuid):
    for el in root.iter():
        if el.get(XML_ID_ATTR) == uuid:
            return el
    return None


def get_most_probable_line_with_uuid(annotated, root, current_uuids_set):
    annotated_tokens = tokenize_words(normalize_whitespace(annotated or ''))
    if not annotated_tokens:
        return None, None, None

    len_a = len(annotated_tokens)
    best_text, best_dist, best_uuid = None, float('inf'), None

    for elem in root.iter():
        tag = etree.QName(elem.tag).localname
        if tag not in {"u", "seg", "note", "s"}:
            continue

        seg_tokens = tokenize_words(flatten_segment_text(elem))
        if not seg_tokens:
            continue

        if len(seg_tokens) >= len_a:
            local_best = min(
                nltk.edit_distance(annotated_tokens, seg_tokens[i:i+len_a])
                for i in range(len(seg_tokens)-len_a+1)
            )
        else:
            local_best = nltk.edit_distance(annotated_tokens, seg_tokens)

        if local_best < best_dist:
            best_dist = local_best
            best_text = flatten_segment_text(elem)
            best_uuid = get_xml_id(elem)

        if best_uuid in current_uuids_set:
            continue
        current_uuids_set.add(best_uuid)

        if best_dist == 0:
            break

    return best_text, best_dist, best_uuid


def process_non_speaker_row(args):
    row, data_dir, current_uuids = args
    protocol_id = row['protocol_id'].strip()
    parent_uuid = row.get('uuid')
    text = row.get('intro_text', '')

    if protocol_id not in current_uuids:
        current_uuids[protocol_id] = set()

    xml_path = os.path.join(data_dir, os.path.relpath(protocol_id, "data"))
    if not os.path.exists(xml_path):
        return {'protocol_id': protocol_id, 'reason': 'file_not_found', 'uuid': parent_uuid}

    try:
        root, _ = parse_tei(xml_path)
    except Exception as e:
        return {'protocol_id': protocol_id, 'reason': f'parse_error:{e}', 'uuid': parent_uuid}

    el = find_element_by_xml_id(root, parent_uuid)
    if el is None:
        _, _, rescued_uuid = get_most_probable_line_with_uuid(text, root, current_uuids[protocol_id])
        return {'protocol_id': protocol_id, 'reason': 'uuid_missing', 'new_candidate_uuid': rescued_uuid}

    tag = etree.QName(el).localname
    el_type = (el.get("type") or "").strip()

    if tag == "u" and el_type == "speaker":
        return {'protocol_id': protocol_id, 'reason': 'unexpected_speaker_tag', 'uuid': get_xml_id(el)}

    return None


class TestNonSpeakerMapping(unittest.TestCase):
    data_dir = 'data'
    output_dir = os.path.join('test', 'output')
    non_speaker_dir = os.path.join('test', 'data', 'speaker-segments', 'non-speaker')
    existing_uuids: Dict[str, set] = {}
    xml_cache: Dict[str, etree._Element] = {}

    def _collect_rows(self, directory):
        dfs = []
        for fname in os.listdir(directory):
            if fname.endswith('.tsv'):
                df = pd.read_csv(os.path.join(directory, fname), sep='\t', dtype=str).fillna('')
                dfs.append(df)
        if dfs:
            df = pd.concat(dfs, ignore_index=True, sort=False)
            self.existing_uuids = {pid: set(subdf['uuid']) for pid, subdf in df.groupby('protocol_id')}
            return df
        return pd.DataFrame()

    def test_non_speaker_segments(self, multiprocess=False):
        df = self._collect_rows(self.non_speaker_dir)
        results = []

        args_list = [(row, self.data_dir, self.existing_uuids) for _, row in df.iterrows()]

        if multiprocess:
            with Pool() as pool:
                for res in tqdm(pool.imap_unordered(process_non_speaker_row, args_list), total=len(args_list)):
                    if res:
                        results.append(res)
        else:
            for args in tqdm(args_list):
                res = process_non_speaker_row(args)
                if res:
                    results.append(res)

        os.makedirs(self.output_dir, exist_ok=True)
        output_file = os.path.join(self.output_dir, 'non_speaker_failures.tsv')
        if results:
            pd.DataFrame(results).to_csv(output_file, sep='\t', index=False)
            print(f"Non-speaker test failures logged in {output_file}")
        else:
            print("All non-speaker tests passed successfully!")

        assert not results, "Non-speaker mapping failures detected."

    def tearDown(self):
        """Clear cached resources after test run."""
        self.existing_uuids.clear()
        self.xml_cache.clear()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run non-speaker mapping tests")
    parser.add_argument('--multiprocess', action='store_true', help='Use multiprocessing for faster local runs')
    args = parser.parse_args()

    test_suite = TestNonSpeakerMapping()
    test_suite.test_non_speaker_segments(multiprocess=args.multiprocess)
    test_suite.tearDown()