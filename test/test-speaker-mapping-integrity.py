import os
import re
import unittest
import pandas as pd
from lxml import etree
from multiprocessing import Pool, cpu_count
from tqdm import tqdm


def infer_year_from_protocol(protocol_id: str) -> str:
    """Extract the part between the first and second dash."""
    m = re.match(r'^prot-([^-]+)-', protocol_id)
    if not m:
        raise ValueError(f"Cannot infer year from protocol_id: {protocol_id}")
    return m.group(1)


def parse_tei(path: str):
    """Basic XML parser with TEI namespace."""
    parser = etree.XMLParser(remove_blank_text=True)
    root = etree.parse(path, parser).getroot()
    ns = {
        'tei': 'http://www.tei-c.org/ns/1.0',
        'xml': 'http://www.w3.org/XML/1998/namespace'
    }
    return root, ns


def find_element_by_xml_id(root: etree._Element, uuid: str) -> etree._Element:
    """Find element with xml:id == uuid."""
    xml_id_attr = '{http://www.w3.org/XML/1998/namespace}id'
    for el in root.iter():
        if el.get(xml_id_attr) == uuid:
            return el
    return None


def check_row_integrity(row, data_dir):
    """Perform the integrity check for one CSV row."""
    result = {"status": "ok", "row": row.to_dict(), "reason": ""}
    try:
        protocol_id = row['protocol_id']
        uuid = row['uuid']
        person_id = row['person_id']
        is_intro = str(row['is_intro']).strip()

        try:
            year = infer_year_from_protocol(protocol_id)
        except ValueError:
            result["status"] = "xml_id_not_found"
            result["reason"] = "Cannot infer year"
            return result

        file_path = os.path.join(data_dir, year, protocol_id)
        if not os.path.exists(file_path):
            result["status"] = "xml_id_not_found"
            result["reason"] = "File not found"
            return result

        try:
            root, ns = parse_tei(file_path)
        except Exception as e:
            result["status"] = "xml_id_not_found"
            result["reason"] = f"Parse error: {e}"
            return result

        el = find_element_by_xml_id(root, uuid)
        if el is None:
            result["status"] = "xml_id_not_found"
            result["reason"] = "UUID not found"
            return result

        who = el.get("who")
        type_attr = el.get("type")

        if is_intro == "1":
            if who != person_id or type_attr != "speaker":
                result["status"] = "not_a_speaker"
                result["reason"] = f"Expected who={person_id}, type='speaker' but got who={who}, type={type_attr}"
        else:
            if who == "unknown" or type_attr == "speaker":
                result["status"] = "speaker_removed"
                result["reason"] = f"Unexpected who={who} or type={type_attr}"

        return result
    except Exception as e:
        result["status"] = "error"
        result["reason"] = str(e)
        return result


def _worker_check(args):
    """Top-level helper for multiprocessing."""
    row, data_dir = args
    return check_row_integrity(row, data_dir)


class TestSpeakerMappingIntegrity(unittest.TestCase):
    def setUp(self):
        self.csv_path = os.path.join("test", "data", "speaker-mapping-unknowns-to-knowns.csv")
        self.data_dir = "data"
        self.output_dir = os.path.join("test", "output")
        os.makedirs(self.output_dir, exist_ok=True)
        self.df = pd.read_csv(self.csv_path, dtype=str, sep="\t", encoding="utf-8").fillna('')

    def tearDown(self):
        """Optional cleanup after tests."""
        for filename in ["xml_id_not_found.csv", "not_a_speaker.csv", "speaker_removed.csv"]:
            path = os.path.join(self.output_dir, filename)
            if os.path.exists(path):
                os.remove(path)

    def test_speaker_mapping_persistence(self):
        """Ensure speaker mappings remain intact in XML files (parallelized + progress bar)."""
        rows = [row for _, row in self.df.iterrows()]
        n_cores = cpu_count()

        print(f"\nRunning integrity check on {len(rows)} rows using {n_cores} cores...\n")

        with Pool(n_cores) as pool:
            results = list(
                tqdm(
                    pool.imap_unordered(_worker_check, [(row, self.data_dir) for row in rows]),
                    total=len(rows),
                    desc="Checking XML mappings"
                )
            )

        not_a_speaker = [r["row"] for r in results if r["status"] == "not_a_speaker"]
        speaker_removed = [r["row"] for r in results if r["status"] == "speaker_removed"]
        xml_id_not_found = [r["row"] for r in results if r["status"] == "xml_id_not_found"]

        # Write reports
        def write_report(filename, rows):
            out_path = os.path.join(self.output_dir, filename)
            if rows:
                pd.DataFrame(rows).to_csv(out_path, index=False, sep="\t", encoding="utf-8")
            elif os.path.exists(out_path):
                os.remove(out_path)

        write_report("xml_id_not_found.csv", xml_id_not_found)
        write_report("not_a_speaker.csv", not_a_speaker)
        write_report("speaker_removed.csv", speaker_removed)

        print("\nIntegrity check summary:")
        print(f"  Total rows checked       : {len(self.df)}")
        print(f"  XML IDs not found        : {len(xml_id_not_found)}")
        print(f"  Intro speakers mismatched: {len(not_a_speaker)}")
        print(f"  Non-intro violations     : {len(speaker_removed)}")

        errors = len(xml_id_not_found) + len(not_a_speaker) + len(speaker_removed)
        self.assertEqual(errors, 0, f"Integrity test failed with {errors} mismatches. See test/output/*.csv for details.")


if __name__ == "__main__":
    unittest.main()