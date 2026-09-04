# Snabbprotokoll

## Summary

Checks that later parliamentary records are not obvious snabbprotokoll or preliminary protocols.

The test intentionally inspects only document-level metadata, front matter, and opening body title notes. It does not scan the full body text, because final records can legitimately mention snabbprotokoll in speeches, appendices, or procedural notes.

By default, the latest two available parliament years are checked. Set `SNABBPROTOKOLL_START_YEAR` to run the same check from another cutoff year.

## Test Cases

(this section should be populated from docstrings)
