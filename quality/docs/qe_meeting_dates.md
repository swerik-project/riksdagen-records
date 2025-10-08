# Meeting Dates Quality Estimation

## Summary
This module evaluates the quality of automatically extracted **meeting dates** in the Riksdag protocol corpus.  
It compares extracted XML dates with manually annotated gold-standard data and computes **precision**, **recall**, **F1-score**, and the **Jaccard coefficient** to assess performance of automatically identifying dates across years.

---

## Background
Meeting dates in Riksdag protocols are embedded within complex TEI/XML structures.  
They can appear in multiple formats — sometimes within the metadata, sometimes mentioned inside the text or speeches for reference.  
Because of this variation, automatic extraction can confuse contextual mentions with actual meeting dates.  
The quality estimation ensures that such distinctions are correctly handled, and that the date extraction logic remains robust across different years and protocol formats.


## Problem Description
Meeting dates are critical for the Riksdag Library’s ability to retrieve and filter records by time periods.  
To ensure reliability, we need to measure how closely the automatically extracted dates match those manually verified by annotators.

The estimation focuses on:
- The **proportion of correct dates** (precision),
- The **coverage of true dates** (recall),
- The **balance between precision and recall** (F1-score),
- The **overall set similarity** between extracted and gold-standard dates (Jaccard index).

---

## Data and Estimation Procedure
The evaluation relies on **two annotated datasets**:
- `goldstandard-dates-expert.csv`
- `goldstandard-dates-student.csv`

Each record includes:
- `pdf_url`: link to the original protocol,
- `docDate`: manually annotated meeting date(s).

The annotations are combined and compared to dates automatically extracted from XML protocols.  
For each protocol:
- **False negatives (FN)** represent gold-standard dates missing from XML,
- **False positives (FP)** represent extra XML dates not found in the gold standard.

All results are stored under `quality/estimates/record-dates/`.

---

## Sampling Plan
Originally, three protocols per year and chamber were intended for annotation.  
However, because the **parliamentary year** and **calendar year** differ — and the **chamber system** ended in 1970 —  
the effective number of protocols per calendar year varies, but per parliament year matches.  
The resulting combined expert and student sample remains sufficiently representative for estimating quality trends across time.  
This sample is used solely for **quality evaluation**, not for model training.

---

## Metrics and Output
Metrics are calculated **per year** and **overall**, and saved to:

- `date_metrics.csv` — version, year, precision, recall, F1-score, and Jaccard  
- `missing_annotations_fn.csv` — false negatives  
- `wrong_annotations_fp.csv` — false positives  

Plots of all four metrics are automatically saved under `quality/estimates/record-dates/`.  
The `--show` flag can be used to display them interactively.

| Metric | Description |
|--------|--------------|
| **Precision** | Correctly extracted dates / All extracted dates |
| **Recall** | Correctly extracted dates / All gold-standard dates |
| **F1-score** | Harmonic mean of precision and recall |
| **Jaccard coefficient** | Intersection-over-union of extracted and gold-standard date sets |

---

## Implementation Notes
The quality estimation is implemented in **`qe_meeting-dates.py`**, which:
- Merges the expert and student annotation files,
- Compares them with XML-extracted meeting dates,
- Computes metrics per year and overall,
- Supports parallel processing for efficiency,
- Allows version tagging to track reproducibility over time.

The **Jaccard coefficient** was recently added.  
In our current results, Jaccard and precision values are nearly identical — which is expected given the small number of false negatives and strong overlap between extracted and annotated dates.

---

## Annotation Guidelines
Annotators should:
1. Read each protocol and identify all meeting dates.  
2. Record them under the `docDate` column.  
3. Ensure that the `pdf_url` matches the correct protocol file.  
4. Save the final CSV under `quality/data/record-dates/`.

---

## Example Command
```bash
python quality/data/record-dates/qe_meeting-dates.py \
  --annotated-data quality/data/record-dates/goldstandard-dates-expert.csv \
  quality/data/record-dates/goldstandard-dates-student.csv \
  --version v99.99.99 --show```