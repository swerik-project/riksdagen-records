# Snabbprotokoll

## Summary

Checks that later parliamentary records are not obvious snabbprotokoll or preliminary protocols.

The test intentionally inspects only document-level metadata and front matter. It does not scan the full body text, because final records can legitimately mention snabbprotokoll in speeches, appendices, or procedural notes.

By default, records from 2000 onward are checked. Set `SNABBPROTOKOLL_START_YEAR` to run the same check from another year.

## Test Cases

(this section should be populated from docstrings)
