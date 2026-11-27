"""Publication checks for the records repository's canonical YAML and DCAT RDF.
"""

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from urllib.parse import urlsplit

from lxml import etree
from trainerlog import get_logger

from test.repository_info_dcat import load_repository_info, write_dcat_rdf


LOGGER = get_logger(name="repository-info")
INFO_PATH = Path("docs/riksdagen-records-info.yml")
DCAT_PATH = Path("docs/dcat/riksdagen-records.rdf")
REPOSITORY_URL = "https://github.com/swerik-project/riksdagen-records"
NS = {
    "rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
    "dcat": "http://www.w3.org/ns/dcat#",
    "dct": "http://purl.org/dc/terms/",
    "foaf": "http://xmlns.com/foaf/0.1/",
    "vcard": "http://www.w3.org/2006/vcard/ns#",
}


class RepositoryInfoTest(unittest.TestCase):
    def test_metadata_identifies_records(self):
        """Guarantee: the canonical YAML identifies the records repository and dataset."""
        info = load_repository_info(INFO_PATH)
        self.assertEqual(
            (info["repository"]["name"], info["dataset"]["identifier"]),
            ("riksdagen-records", "riksdagen-records"),
            f"{INFO_PATH} must identify the repository and dataset as riksdagen-records.",
        )

    def test_records_zip_distribution_uses_latest_release(self):
        """Guarantee: records.zip has one distribution pointing to the latest release."""
        info = load_repository_info(INFO_PATH)
        records = [
            distribution
            for distribution in info["distributions"]
            if distribution.get("name") == "records.zip"
        ]
        self.assertEqual(len(records), 1, f"{INFO_PATH} must have one records.zip distribution.")

        latest_zip = f"{REPOSITORY_URL}/releases/latest/download/records.zip"
        expected = {
            "access_url": latest_zip,
            "download_url": latest_zip,
            "media_type": "application/zip",
            "format": "ZIP",
        }
        self.assertEqual(
            {key: records[0].get(key) for key in expected},
            expected,
            f"{INFO_PATH} must give records.zip stable ZIP URLs and ZIP metadata.",
        )

    def test_public_metadata_links_are_absolute(self):
        """Guarantee: public RDF links and the YAML issue tracker URL are absolute."""
        rdf = etree.parse(DCAT_PATH)
        urls = rdf.xpath("//@rdf:about | //@rdf:resource", namespaces=NS)
        urls.append(load_repository_info(INFO_PATH)["repository"]["issue_tracker_url"])
        invalid = 0
        for url in urls:
            parsed = urlsplit(url) if isinstance(url, str) else None
            if not parsed or parsed.scheme not in {"http", "https"} or not parsed.hostname:
                LOGGER.error(f"Expected an absolute HTTP(S) publication URL: {url!r}")
                invalid += 1
        self.assertEqual(invalid, 0, f"{invalid} invalid publication URL(s); see log.")

    def test_dcat_core_resources_are_named(self):
        """Guarantee: RDF declares named catalogue, dataset, distribution, publisher and contact resources."""
        rdf = etree.parse(DCAT_PATH)
        errors = 0
        for tag in ("dcat:Catalog", "dcat:Dataset", "dcat:Distribution", "foaf:Agent", "vcard:Organization"):
            resources = rdf.findall(tag, namespaces=NS)
            if not resources:
                LOGGER.error(f"{DCAT_PATH} is missing {tag}.")
                errors += 1
            for resource in resources:
                if not resource.xpath("@rdf:about and not(@rdf:nodeID)", namespaces=NS):
                    LOGGER.error(f"{DCAT_PATH} has an unnamed {tag} at line {resource.sourceline}.")
                    errors += 1
        self.assertEqual(errors, 0, f"{errors} missing or unnamed RDF resource(s); see log.")

    def test_dcat_catalogue_lists_records_dataset(self):
        """Guarantee: the published catalogue points to the records dataset."""
        rdf = etree.parse(DCAT_PATH)
        self.assertEqual(
            rdf.xpath("dcat:Catalog/dcat:dataset/@rdf:resource", namespaces=NS),
            [REPOSITORY_URL],
            f"{DCAT_PATH} must list the records dataset in its catalogue.",
        )

    def test_dcat_coverage_preserves_start_year_precision(self):
        """Guarantee: DCAT represents the start of the records corpus as the year 1867."""
        rdf = etree.parse(DCAT_PATH)
        start = rdf.find("dct:PeriodOfTime/dcat:startDate", namespaces=NS)
        self.assertIsNotNone(start, f"{DCAT_PATH} must include the corpus start year.")
        self.assertEqual(
            (start.text, start.get(f"{{{NS['rdf']}}}datatype")),
            ("1867", "http://www.w3.org/2001/XMLSchema#gYear"),
            f"{DCAT_PATH} must give the start as 1867 with year precision.",
        )

    def test_checked_in_dcat_matches_repository_info(self):
        """Guarantee: the checked-in RDF reflects the canonical YAML.

        Ignore XML indentation and attribute order when comparing the exports.
        """
        parser = etree.XMLParser(remove_blank_text=True)
        checked_in = etree.parse(DCAT_PATH, parser)
        with TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / DCAT_PATH.name
            write_dcat_rdf(INFO_PATH, output)
            generated = etree.parse(output, parser)
        self.assertTrue(
            etree.tostring(checked_in, method="c14n", exclusive=True)
            == etree.tostring(generated, method="c14n", exclusive=True),
            f"{DCAT_PATH} is stale. Regenerate it from {INFO_PATH}.",
        )


if __name__ == "__main__":
    unittest.main()
