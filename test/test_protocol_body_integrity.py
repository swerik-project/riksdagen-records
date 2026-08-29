"""
Data integrity tests for protocol body/content guarantees.

These tests check that yearly protocol XML files contain a TEI ``text`` and a
non-empty TEI ``body``. The body guarantee matters because downstream corpus
users and curation scripts assume that yearly protocol files contain the
parliamentary proceedings, not just header/front-matter stubs.

The tests use the XML corpus in ``data/`` as input and write structured
diagnostics to ``test/results/protocol-body-integrity.csv`` when issues are
found. Tiny files are reported as a separate regression guard because they are
often incomplete, but size alone is not treated as proof that a body is absent.
"""
from pathlib import Path
import unittest

import polars as pl
from pyriksdagen.io import TEI_NS, parse_tei
from pyriksdagen.utils import corpus_iterator
from trainerlog import get_logger


LOGGER = get_logger(name="protocol-body-integrity")
RESULTS_PATH = Path("test/results/protocol-body-integrity.csv")
MIN_PROTOCOL_BYTES = 2048

# Current-data baselines for known structural/content issues. These keep the
# test release-blocking for regressions while allowing later curation PRs to
# ratchet the ceilings down as incomplete records are repaired.
MAX_MISSING_TEXT = 0
MAX_MISSING_BODY = 2
MAX_EMPTY_BODY = 0
MAX_SMALL_FILES = 4

KNOWN_199192_BODY_STUBS = {
    "data/199192/prot-199192--001.xml",
    "data/199192/prot-199192--002.xml",
}

DIAGNOSTIC_COLUMNS = [
    "file",
    "error_type",
    "issue",
    "size_bytes",
    "body_children",
    "body_text_chars",
]

_BODY_ERRORS = None


def empty_error_row():
    return {column: "" for column in DIAGNOSTIC_COLUMNS}


def body_error(error_type, file, issue, **fields):
    row = empty_error_row()
    row.update(
        {
            "file": str(file),
            "error_type": error_type,
            "issue": issue,
            **fields,
        }
    )
    return row


def body_text_length(body):
    if body is None:
        return 0
    return len("".join(body.itertext()).strip())


def body_child_count(body):
    if body is None:
        return 0
    return len(body)


def collect_body_errors():
    errors = []
    protocols = sorted(corpus_iterator("records", corpus_root="data"))
    LOGGER.info("Checking protocol body integrity for %s protocols", len(protocols))

    for path in protocols:
        file_path = Path(path)
        size_bytes = file_path.stat().st_size
        root, _ = parse_tei(path)
        text = root.find(f".//{TEI_NS}text")
        body = root.find(f".//{TEI_NS}body")
        text_length = body_text_length(body)
        child_count = body_child_count(body)

        common_fields = {
            "size_bytes": str(size_bytes),
            "body_children": str(child_count),
            "body_text_chars": str(text_length),
        }

        if text is None:
            errors.append(
                body_error(
                    "missing_text",
                    path,
                    "missing TEI text element",
                    **common_fields,
                )
            )

        if body is None:
            errors.append(
                body_error(
                    "missing_body",
                    path,
                    "missing TEI body element",
                    **common_fields,
                )
            )
        elif child_count == 0 and text_length == 0:
            errors.append(
                body_error(
                    "empty_body",
                    path,
                    "TEI body has no child elements or text",
                    **common_fields,
                )
            )

        if size_bytes < MIN_PROTOCOL_BYTES:
            errors.append(
                body_error(
                    "small_file",
                    path,
                    f"protocol XML smaller than {MIN_PROTOCOL_BYTES} bytes",
                    **common_fields,
                )
            )

    return errors


def body_errors():
    global _BODY_ERRORS

    if _BODY_ERRORS is None:
        errors = collect_body_errors()
        _BODY_ERRORS = pl.DataFrame(errors, schema=DIAGNOSTIC_COLUMNS)
        if len(_BODY_ERRORS) > 0:
            RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
            _BODY_ERRORS = _BODY_ERRORS.sort(["file", "error_type"])
            _BODY_ERRORS.write_csv(RESULTS_PATH)

    return _BODY_ERRORS


def errors_of_type(error_type):
    return body_errors().filter(pl.col("error_type") == error_type)


def test_protocols_have_text_elements():
    """Every yearly protocol should have a TEI text element."""
    df_missing_text = errors_of_type("missing_text")
    assert len(df_missing_text) <= MAX_MISSING_TEXT, (
        f"{len(df_missing_text)} protocol(s) are missing TEI text elements, "
        f"exceeding baseline {MAX_MISSING_TEXT}; see {RESULTS_PATH}"
    )


def test_protocols_have_body_elements():
    """Every yearly protocol should have a TEI body element."""
    df_missing_body = errors_of_type("missing_body")
    assert len(df_missing_body) <= MAX_MISSING_BODY, (
        f"{len(df_missing_body)} protocol(s) are missing TEI body elements, "
        f"exceeding baseline {MAX_MISSING_BODY}; see {RESULTS_PATH}"
    )


def test_protocol_bodies_are_not_empty():
    """Protocol body elements should contain child elements or text."""
    df_empty_body = errors_of_type("empty_body")
    assert len(df_empty_body) <= MAX_EMPTY_BODY, (
        f"{len(df_empty_body)} protocol body element(s) are empty, "
        f"exceeding baseline {MAX_EMPTY_BODY}; see {RESULTS_PATH}"
    )


def test_protocol_files_are_not_suspiciously_small():
    """Tiny protocol files should not increase without review."""
    df_small = errors_of_type("small_file")
    assert len(df_small) <= MAX_SMALL_FILES, (
        f"{len(df_small)} protocol XML file(s) are smaller than "
        f"{MIN_PROTOCOL_BYTES} bytes, exceeding baseline {MAX_SMALL_FILES}; "
        f"see {RESULTS_PATH}"
    )


def test_known_199192_body_stubs_are_reported():
    """Known issue-234 body stubs should be visible in diagnostics until fixed."""
    reported = set(errors_of_type("missing_body").get_column("file").to_list())
    missing = []
    for path in KNOWN_199192_BODY_STUBS:
        if not Path(path).exists():
            continue
        root, _ = parse_tei(path)
        if root.find(f".//{TEI_NS}body") is None and path not in reported:
            missing.append(path)

    assert not missing, (
        "known issue-234 protocol body stubs were not reported: "
        f"{missing}; see {RESULTS_PATH}"
    )


def load_tests(loader, tests, pattern):
    suite = unittest.TestSuite()
    suite.addTest(unittest.FunctionTestCase(test_protocols_have_text_elements))
    suite.addTest(unittest.FunctionTestCase(test_protocols_have_body_elements))
    suite.addTest(unittest.FunctionTestCase(test_protocol_bodies_are_not_empty))
    suite.addTest(
        unittest.FunctionTestCase(test_protocol_files_are_not_suspiciously_small)
    )
    suite.addTest(unittest.FunctionTestCase(test_known_199192_body_stubs_are_reported))
    return suite


if __name__ == "__main__":
    unittest.main()
