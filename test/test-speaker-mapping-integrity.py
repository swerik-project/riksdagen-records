#!/usr/bin/env python3
"""
Test suite for validating speaker propagation in TEI XML protocols.

Checks:
1. Every element assigned a speaker (<u>, <seg>, <note>) has the correct WHO attribute.
2. Nested elements inherit the correct speaker assignment.
3. Speaker propagation along <u next="..."> chains is consistent.
4. Fallback to standard sibling traversal (<u> elements) works if next chains are missing.
5. Any mismatches or missing UUIDs are logged for review.

Supports sequential execution (default) or multiprocessing with --multiprocess flag.
"""
import os
import re
import unittest
import pandas as pd
from lxml import etree
from tqdm import tqdm
import nltk
import argparse
from pyriksdagen.io import parse_tei

XML_NS = "http://www.w3.org/XML/1998/namespace"
XML_ID_ATTR = f"{{{XML_NS}}}id"


def get_xml_id(elem):
    """Return the XML ID of an element, or a placeholder if missing."""
    return elem.get(XML_ID_ATTR) or elem.get("id") or "[NOUUID]"


def normalize_whitespace(s):
    """Collapse all whitespace into single spaces."""
    return " ".join(s.split()) if s else ""


def tokenize_words(s):
    """Split string into lowercase word tokens."""
    return [w for w in re.findall(r"\w+", (s or "").lower()) if w]


def flatten_segment_text(elem):
    """Concatenate all text in an element and its children, normalized."""
    parts = [elem.text.strip()] if elem.text and elem.text.strip() else []
    for child in elem:
        if child.text and child.text.strip():
            parts.append(child.text.strip())
        if child.tail and child.tail.strip():
            parts.append(child.tail.strip())
    return normalize_whitespace(" ".join(parts))


def get_most_probable_line_with_uuid(annotated, root, seen_uuids):
    """Find the element in the XML that best matches the annotated text."""
    annotated_tokens = tokenize_words(normalize_whitespace(annotated or ""))
    if not annotated_tokens:
        return None, None, None

    len_a = len(annotated_tokens)
    best_text, best_dist, best_uuid = None, float("inf"), None

    for elem in root.iter():
        tag = etree.QName(elem.tag).localname
        if tag not in {"u", "seg", "note", "s"}:
            continue

        seg_tokens = tokenize_words(flatten_segment_text(elem))
        if not seg_tokens:
            continue

        if len(seg_tokens) >= len_a:
            local_best = min(
                nltk.edit_distance(annotated_tokens, seg_tokens[i:i + len_a])
                for i in range(len(seg_tokens) - len_a + 1)
            )
        else:
            local_best = nltk.edit_distance(annotated_tokens, seg_tokens)

        if local_best < best_dist:
            best_dist = local_best
            best_text = flatten_segment_text(elem)
            best_uuid = get_xml_id(elem)

        if best_uuid in seen_uuids:
            continue

        seen_uuids.add(best_uuid)

        if best_dist == 0:
            break

    return best_text, best_dist, best_uuid


def find_element_by_xml_id(root, uuid):
    """Return the element with the given XML ID, or None."""
    for el in root.iter():
        if el.get(XML_ID_ATTR) == uuid:
            return el
    return None


def is_relevant(el):
    """Check if the element is one of the relevant types for WHO checks."""
    return etree.QName(el.tag).localname in {"u", "seg", "note"}


def get_tag(el):
    """Return the local tag name of the element."""
    return etree.QName(el.tag).localname


class TestSpeakerPropagationIntegrity(unittest.TestCase):

    data_dir = "data"
    base_dir = os.path.join("test", "data", "speaker-segments", "is-speaker")
    output_file = os.path.join("test", "output", "is_speaker_failures.tsv")
    xml_cache = {}
    uuid_memory = {}

    def tearDown(self):
        """Clean up cached resources after each test method."""
        self.xml_cache.clear()
        self.uuid_memory.clear()

    def load_xml(self, protocol_id):
        """Parse and cache the XML for a protocol."""
        if protocol_id not in self.xml_cache:
            xml_path = os.path.join(self.data_dir, os.path.relpath(protocol_id, "data"))
            root, _ = parse_tei(xml_path)
            self.xml_cache[protocol_id] = root
            self.uuid_memory[protocol_id] = set()
        return self.xml_cache[protocol_id]

    def load_is_speaker_rows(self):
        """Load all speaker mapping TSVs, grouped by protocol."""
        dfs = []
        for fname in os.listdir(self.base_dir):
            if fname.endswith(".tsv"):
                df = pd.read_csv(os.path.join(self.base_dir, fname),
                                 sep="\t", dtype=str).fillna("")
                dfs.append(df)
        all_df = pd.concat(dfs, ignore_index=True)
        return {pid: sub for pid, sub in all_df.groupby("protocol_id")}

    def validate_recursive_children(self, el, expected_who):
        """Check recursively that all child nodes have the correct WHO and note type."""
        for node in el.iter():
            if not is_relevant(node):
                continue
            who = node.get("who")
            if who != expected_who:
                return False, f"WHO mismatch: {who} != {expected_who}"
            if get_tag(node) == "note" and node.get("type") != "speaker":
                return False, "<note> not type='speaker'"
        return True, None

    def validate_sibling_chain(self, el, expected_who):
        """
        Validate that speaker propagation continues correctly.
        1. Follow the <u next="..."> chain if present.
        2. Otherwise, follow standard sibling <u> elements.
        Returns False if a mismatch is found.
        """
        visited = set()
        nxt = el

        while nxt is not None:
            nxt_id = nxt.get("next")
            if not nxt_id:
                break

            root = nxt.getroottree().getroot()
            nxt_elem = find_element_by_xml_id(root, nxt_id)
            if nxt_elem is None or nxt_id in visited:
                break
            visited.add(nxt_id)

            if get_tag(nxt_elem) == "u":
                who = nxt_elem.get("who")
                if who and who != expected_who:
                    return False, (
                        f"<u next> WHO mismatch: {who} != {expected_who} "
                        f"at {nxt_elem.get(XML_ID_ATTR)}"
                    )
            nxt = nxt_elem

        nxt = el.getnext()
        while nxt is not None:
            if get_tag(nxt) == "u":
                who = nxt.get("who")
                if who and who != expected_who:
                    return False, (
                        f"Sibling <u> WHO mismatch: {who} != {expected_who} "
                        f"at {nxt.get(XML_ID_ATTR)}"
                    )
                break
            nxt = nxt.getnext()

        return True, None

    def test_speaker_propagation_full(self):
        """Full test: check all speaker assignments and log failures."""
        grouped = self.load_is_speaker_rows()
        failures = []

        for protocol_id, df in tqdm(grouped.items(), desc="Validating speaker mapping"):
            root = self.load_xml(protocol_id)

            for _, row in df.iterrows():
                uuid = row["uuid"]
                person_id = row["person_id"]
                annotated = row.get("intro_text", "")

                el = find_element_by_xml_id(root, uuid)
                if el is None:
                    _, _, new_uuid = get_most_probable_line_with_uuid(
                        annotated, root, self.uuid_memory[protocol_id]
                    )
                    failures.append((protocol_id, uuid, person_id,
                                     "UUID not found in TEI",
                                     new_uuid if new_uuid else "-"))
                    continue

                ok, reason = self.validate_recursive_children(el, person_id)
                if not ok:
                    failures.append((protocol_id, uuid, person_id, reason, "-"))
                    continue

                ok, reason = self.validate_sibling_chain(el, person_id)
                if not ok:
                    failures.append((protocol_id, uuid, person_id, reason, "-"))
                    continue

        os.makedirs(os.path.dirname(self.output_file), exist_ok=True)
        if failures:
            pd.DataFrame(
                failures,
                columns=["protocol_id", "uuid", "person_id", "reason", "new_candidate_uuid"]
            ).to_csv(self.output_file, sep="\t", index=False)

        assert not failures, f"Failures logged in {self.output_file}"


def main(args):
    """Run the test suite with optional multiprocessing."""
    if args.multiprocess:
        unittest.main(verbosity=2, failfast=False, buffer=True)
    else:
        unittest.main(verbosity=2)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Validate speaker propagation in TEI XML protocols.")
    parser.add_argument("--multiprocess", action="store_true",
                        help="Run tests using multiprocessing")
    args = parser.parse_args()
    main(args)