# Test Data

This folder contains small reference and fixture files used by
`riksdagen-records` data integrity tests.

## `riksdag-year.csv`

`riksdag-year.csv` is a copy of:

```text
../riksdagen-persons/data/riksdag-year.csv
```

It is vendored here so CI can run date-range integrity tests with the same
Riksdag-year boundaries as local checkouts, without requiring a sibling
`riksdagen-persons` checkout.

To update it, copy the current file from `riksdagen-persons`:

```bash
cp ../riksdagen-persons/data/riksdag-year.csv test/data/riksdag-year.csv
```
