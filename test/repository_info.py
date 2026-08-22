#!/usr/bin/env python3
"""
Validate repository-level publication metadata.

This test checks the repository publication metadata guarantee introduced by
SWERIK decision 0023: the canonical repository info file must exist at
docs/[repo-name]-info.yml, have the expected top-level structure, agree with
the repository name, and use absolute URLs for public resources.

This matters because DCAT, release-page summaries, catalogue records, and other
publication artifacts should be generated from one stable source rather than
from copied hand-maintained metadata. The test reads only the repository info
YAML file in docs/. Fuller documentation is in test/docs/repository_info.md.
"""

from pathlib import Path
from urllib.parse import urlparse
import sys
import unittest

import yaml


REQUIRED_TOP_LEVEL_KEYS = {
    "metadata_type",
    "metadata_version",
    "repository",
    "dataset",
    "publisher",
    "contact",
    "documentation",
    "citation",
    "distributions",
    "relations",
}

REQUIRED_PATHS = (
    ("repository", "name"),
    ("repository", "url"),
    ("repository", "issue_tracker_url"),
    ("dataset", "identifier"),
    ("dataset", "title", "en"),
    ("dataset", "title", "sv"),
    ("dataset", "description", "en"),
    ("dataset", "description", "sv"),
    ("dataset", "languages"),
    ("dataset", "keywords", "en"),
    ("dataset", "keywords", "sv"),
    ("dataset", "type"),
    ("publisher", "name", "en"),
    ("publisher", "name", "sv"),
    ("publisher", "url"),
    ("contact", "name"),
    ("contact", "email"),
    ("contact", "url"),
    ("documentation", "readme_url"),
    ("citation", "cff_url"),
    ("distributions",),
    ("relations", "related_repositories"),
)

LIST_PATHS = (
    ("dataset", "languages"),
    ("dataset", "keywords", "en"),
    ("dataset", "keywords", "sv"),
    ("distributions",),
    ("relations", "related_repositories"),
)


def repository_root():
    return Path(__file__).resolve().parents[1]


def info_path(repo_root=None):
    repo_root = repo_root or repository_root()
    return repo_root / "docs" / f"{repo_root.name}-info.yml"


def load_repository_info(path=None):
    path = path or info_path()
    with path.open(encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    if not isinstance(data, dict):
        raise AssertionError(f"{path} must contain a YAML mapping")
    return data


def get_path(data, path):
    current = data
    for key in path:
        if not isinstance(current, dict) or key not in current:
            dotted = ".".join(path)
            raise AssertionError(f"Missing required repository info field: {dotted}")
        current = current[key]
    return current


def iter_url_values(value, path=()):
    if isinstance(value, dict):
        for key, nested in value.items():
            yield from iter_url_values(nested, path + (str(key),))
    elif isinstance(value, list):
        for index, nested in enumerate(value):
            yield from iter_url_values(nested, path + (str(index),))
    elif isinstance(value, str) and path:
        key = path[-1]
        parent = path[-2] if len(path) > 1 else ""
        if (
            key == "url"
            or key.endswith("_url")
            or parent.endswith("_repositories")
        ):
            yield path, value


def is_absolute_url(value):
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


class RepositoryInfoTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.repo_root = repository_root()
        cls.path = info_path(cls.repo_root)
        cls.data = load_repository_info(cls.path)

    def test_expected_file_exists(self):
        """Check that the canonical repository info file is present."""
        self.assertTrue(self.path.exists(), f"Expected repository info file at {self.path}")

    def test_top_level_structure(self):
        """Check the common top-level slots and metadata marker fields."""
        missing = REQUIRED_TOP_LEVEL_KEYS.difference(self.data)
        self.assertFalse(missing, f"Missing top-level repository info keys: {sorted(missing)}")
        self.assertEqual(
            self.data["metadata_type"],
            "repository_information",
            "metadata_type must identify this as repository_information",
        )
        self.assertIsInstance(
            self.data["metadata_version"],
            int,
            "metadata_version must be an integer schema version",
        )
        self.assertGreaterEqual(
            self.data["metadata_version"],
            1,
            "metadata_version must be at least 1",
        )

    def test_repository_name_and_file_name_agree(self):
        """Check that the filename, repository name, and dataset identifier agree."""
        repository_name = get_path(self.data, ("repository", "name"))
        self.assertEqual(
            repository_name,
            self.repo_root.name,
            "repository.name must match the local repository directory name",
        )
        self.assertEqual(
            self.path.name,
            f"{repository_name}-info.yml",
            "Repository info filename must follow docs/[repo-name]-info.yml",
        )
        self.assertEqual(
            get_path(self.data, ("dataset", "identifier")),
            repository_name,
            "dataset.identifier must match repository.name",
        )

    def test_required_fields_are_present(self):
        """Check that the draft metadata file contains all required paths."""
        for path in REQUIRED_PATHS:
            get_path(self.data, path)

    def test_list_fields_are_lists(self):
        """Check that repeatable metadata fields are represented as YAML lists."""
        for path in LIST_PATHS:
            value = get_path(self.data, path)
            self.assertIsInstance(value, list, f"{'.'.join(path)} must be a list")

    def test_distribution_fields_are_present(self):
        """Check that release artifact entries include the fields generators need."""
        for distribution in get_path(self.data, ("distributions",)):
            self.assertIsInstance(distribution, dict, "Each distribution must be a mapping")
            for key in ("name", "download_url", "media_type", "format"):
                self.assertIn(key, distribution, f"Distribution is missing required key: {key}")

    def test_present_public_urls_are_absolute(self):
        """Check that public URL fields are absolute when they are filled in."""
        for path, value in iter_url_values(self.data):
            if value == "":
                continue
            dotted = ".".join(path)
            self.assertTrue(is_absolute_url(value), f"{dotted} must be an absolute HTTP(S) URL")


if __name__ == "__main__":
    sys.exit(unittest.main())
