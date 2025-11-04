# Optical Character Recognition (OCR) Error

## Summary

The goal is to estimate the total OCR error in the riksdagen-records corpus. OCR quality can vary across years and protocols, so a stratified cluster sampling design is used with pages as clusters, and year/chamber/protocol as strata. The evaluation estimates line- and page-level deviations and aggregates metrics per year and version.

> **Note:** While the current reference implementation is in Python (`qe_ocr-estimation.py`), the theoretical framework can be applied independently of this code.

---

## Theory and Metrics

This chapter focuses on ....

### Problem Definition

OCR error is a form of textual representation error in total corpus quality frameworks and affects validity of downstream analyses. This work follows the conceptualization of total corpus error in [Hurtado Bodell, Magnusson & Müntzel (2022)](https://raw.githubusercontent.com/swerik-project/swerik-reference-list/refs/heads/main/bibfiles/HurtadoBodellMagnussonMutzel2022.bib). The quality of the OCR is important in many research applications that rely on the text being correct.

--- 

### Term Definitions

We measure OCR quality using string- and token-based distances and error rates:

- **Levenshtein distance ($LEV$):** edit distance between an annotated reference line and the most probable OCR line.
- **Word Error Rate ($WER$):** token-level Levenshtein normalized by reference token count.
- **Character Error Rate ($CER$):** character-level Levenshtein normalized by reference character length.
- **Perfect Match Ratio:** proportion of lines with LEV=0.

---

### Notation and Formulas

Let the reference (annotated) line (or so called gold-standard) be $r$ and the hypothesis (line in the xml file) (OCR candidate) be $h$.

- **Levenshtein distance:**

  $$
  LEV(r, h)
  $$

- Tokenization yields token sequences $T(r)$ and $T(h)$.

- **Word Error Rate (WER):**

  $$
  WER = \frac{LEV(T(r),\, T(h))}{|T(r)|}
  $$

  with the conventions:
  - $WER = 1.0$ if $|T(r)| = 0$ and $T(h)$ is non-empty  
  - $WER = 0.0$ if both are empty

- **Character Error Rate (CER):**

  $$
  CER = \frac{LEV(r,\, h)}{\max(|r|,\, 1)}
  $$

$LEV$, $WER$, and $CER$ are computed per sampled line and aggregated (means, 25th and 75th percentiles) per year.  
Perfect match ratio is the share of sampled lines with $LEV = 0$.

---


## Sampling and Annotation Procedure

This is a stratified cluster sample, where the scanned page is the cluster, and strata are year, chamber and protocol.

---

### Sampling Steps

1. Sample three pages per year, chamber and protocol using stratified clustering approach.

2. On each sampled page the annotator counts NROWS = total number of body-text rows (treat each column-row pair as a separate row for two-column pages).

3. The annotator randomly samples three rows per page; on two-column pages sample three full lines per column (six rows total).

--- 

### Annotation Guidelines

1. Annotators receive a CSV file with page link(s) and sampled row indices.

2. For each sampled row, record the exact line content in the csv (type it over to the file), one sampled line per CSV row, in sampling order.

3. Ensure the CSV row contains the correct page link and protocol identifier.

--- 

### Remarks

Quality-control annotations for the OCR were produced by students at Uppsala University.

--- 

## References

[Hurtado Bodell, Magnusson & Müntzel 2022](https://raw.githubusercontent.com/swerik-project/swerik-reference-list/refs/heads/main/bibfiles/HurtadoBodellMagnussonMutzel2022.bib)

```bibtex
@article{HurtadoBodellMagnussonMuntzel2022,
    author = {Hurtado Bodell, Miriam AND Magnusson, Måns AND Mützel, Sophie},
    title ={From Documents to Data: A Framework for Total Corpus Quality},
    journal = {Socius},
    volume = {8},
    pages = {23780231221135523},
    year = {2022},
    doi = {10.1177/23780231221135523},
    URL = {https://doi.org/10.1177/23780231221135523},
    eprint = {https://doi.org/10.1177/23780231221135523},
    abstract = { As large corpora of digitized text become increasingly available, researchers are rediscovering textual data’s potential fruitfulness for inquiries into social and cultural phenomena. Although textual corpora promise to enrich our knowledge of the social world, avoiding problems related to data quality remains a challenge to related empirical research. Hence, evaluating the quality of a corpus will be pivotal for future social scientific inquiries. The authors propose a conceptual framework for total corpus quality, incorporating three crucial dimensions: total corpus error, corpus comparability, and corpus reproducibility. These dimensions affect the validity and reliability of inferences drawn from textual data. In addition, the authors’ framework provides insights toward evaluating and improving studies on the basis of large-scale textual analyses. After outlining this framework, the authors then illustrate an application of the total corpus quality framework by an example case study using digitized newspaper articles to study topic salience over 75 years. }
}
```

---

## The Code: Matching Algorithm and Implementation Notes

The implementation can be found in the file `./quality/qe_ocr-estimation.py`.

### Hybrid Search Procedure

1. **Normalize text:** collapse whitespace and normalize dashes; preserve case.  
2. **Join segments:** build a single string  
   $$
   \text{seg\_text} = \text{join}(S)
   $$
3. **Exact substring check:**  
   If $a$ appears verbatim in `seg_text`, then $h^* = a$ and $LEV = 0$.  
4. **Token sliding window:**  
   - Tokenize $a$ into $n$ tokens.  
   - Slide an $n$-token window over the tokenized segments.  
   - Compute token-level Levenshtein for each candidate and keep the minimum.  
5. **Character sliding window:**  
   - Slide a character-length window across `seg_text` (with margin).  
   - Compute character-level Levenshtein and keep the minimum.  
6. **Select best match:**  
   Choose the candidate with the smallest $LEV$ and record the method used (`substring`, `token`, or `char`).

### Outputs per Annotation

- `most_probable_line` — matched OCR text  
- `lev` — $LEV(a, h^*)$ (integer)  
- `method` — matching method: `substring` | `token` | `char`

### Aggregation

For each sampled line, compute:
- `lev`, `wer`, `cer`
- `perfect_match = 1` if `lev == 0`, else `0`

Then group by year and calculate:
- `lev_mean`, `lev_first_q` (25th), `lev_third_q` (75th)  
- `wer_mean`, `wer_first_q`, `wer_third_q`  
- `cer_mean`, `cer_first_q`, `cer_third_q`  
- `perfect_match_ratio`, `token_ratio`, `char_ratio`

Finally, save versioned CSV outputs and generate per-year comparison plots in the folder `quality/estimates/ocr-estimation`

### Code and Usage

The script:

- Reads annotated CSV samples  
- Resolves TEI XML and page-level segments  
- Finds the most probable OCR line per annotation  
- Computes LEV, WER, CER, and perfect-match metrics  
- Aggregates by year and writes versioned metrics  
- Generates plots comparing years across versions  
- Supports parallel processing and configurable behaviour  

### Common Flags

- `--annotated-data` — path to CSVs with sampled annotations  
- `--estimate-path` — output folder for metrics and plots  
- `--read-lev` — read precomputed most probable lines and LEV from file  
- `--lev-only` / `--concat-lev` — control LEV-only outputs or concatenated LEV exports  
- `--skip-second-search` / `--lev-threshold` — tune re-search behaviour when LEV is large


### Example full command

```bash
python3 ./quality/qe_ocr-estimation.py \
  --annotations ./data/annotations.csv \
  --tei_dir ./data/tei/ \
  --output ./results/ocr_quality_v2/ \
  --n_jobs 8
```