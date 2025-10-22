# Meeting Dates Quality Estimation

## Summary
This module evaluates the quality of automatically extracted **meeting dates** in the Riksdag protocol corpus.  
The evaluation compares automatically extracted dates from XML against manually annotated **gold-standard dates**, computing **precision**, **recall**, **accuracy**, **coverage**, **F1-score**, and the **Jaccard coefficient** to measure date extraction quality over time.  

> Note: While the current reference implementation is in Python (`qe_meeting-dates.py`), the theoretical framework can be applied independently of this code.

---

## Background
Meeting dates in Riksdag protocols are embedded in TEI/XML structures and can appear in multiple locations:

- In metadata sections  
- Within the textual body (for reference or context)  

Automatic extraction may confuse contextual mentions with actual meeting dates.  
**Quality estimation** ensures that:

1. Only true meeting dates are captured.  
2. Extraction errors (missing or extra dates) are measured systematically.  
3. The extraction logic can be compared across years and versions of the protocols.

---

## Definitions

- **Protocol:** A complete XML document containing one or more dates.  
- **Record:** A section of a protocol associated with a single date and its corresponding text.  

- **Metrics are calculated at two levels:**
  - **Protocol level:** Evaluates the set of all dates in a protocol — Jaccard coefficient, accuracy, and coverage.
  - **Record level:** Evaluates each record individually — precision, recall, and F1-score.
 
---

## Theoretical Framework

Let:

- $D$ = set of gold-standard dates in a record or protocol  
- $\hat{D}$ = set of automatically extracted dates  

We define:

- **True Positives $TP$:** Dates correctly extracted  $TP=|D\cap\hat{D}|.$

- **False Negatives $FN$:** Dates present in the gold standard but missing in extraction $FN = |D\setminus\hat{D}|$

- **False Positives $FP$:** Dates extracted but not present in the gold standard  $FP = |\hat{D}\setminus D| $

### Record-level Metrics

These metrics are calculated **per record** and then aggregated per year or overall:

- **Precision $P$**: Fraction of extracted dates that are correct  
$P = \frac{TP}{TP + FP} \quad \text{with } P = 0 \text{ if } TP + FP = 0$

- **Recall $R$**: Fraction of gold-standard dates correctly extracted  
$R = \frac{TP}{TP + FN} \quad \text{with } R = 0 \text{ if } TP + FN = 0$

- **F1-score $F_1$**: Harmonic mean of precision and recall  
$F_1 = \frac{2 \cdot P \cdot R}{P + R} \quad \text{with } F_1 = 0 \text{ if } P + R = 0 $

### Protocol-level Metrics

These metrics are calculated **per protocol**, treating all dates in the protocol as a set:

- **Jaccard Coefficient $J$**: Set-based similarity

$$ J = \frac{|D \cap \hat{D}|}{|D \cup \hat{D}|} $$

- **Accuracy**: Fraction of protocols where all dates match exactly  

$$\text{Accuracy} = \frac{\text{Number of protocols with } J = 1}{\text{Total number of protocols}}$$

- **Coverage**: Fraction of protocols where all gold-standard dates are captured (extra dates allowed)  

$$\text{Coverage} = \frac{\text{Number of protocols with } D \subseteq \hat{D}}{\text{Total number of protocols}}$$

> Accuracy reflects **strict matching**, coverage reflects **relaxed matching**, and Jaccard combines both perspectives.

---

## Data and Annotation

The evaluation uses **two annotated datasets**:

| File | Annotator(s) |
|------|--------------|
| `goldstandard-dates-expert.csv` | Fredrik Mohammadi Norén and Lotta Åberg Brorsson |
| `goldstandard-dates-student.csv` | Theodora Moldovan |

Each record contains:

- `pdf_url`: Link to the original protocol  
- `docDate`: Manually annotated date(s)  

> The Python code merges these datasets to form a combined gold standard.

---

## Sampling Plan

A **stratified random sampling** approach ensures representativeness across:

- **Years** (calendar and parliamentary years)  
- **Chambers** (historical relevance; note that the chamber system ended in 1970)

---

## Metrics and Output

Metrics are calculated **per year** and **overall**, and saved to:

- `record_metrics.csv` — version, year, precision, recall, F1-score  
- `protocol_metrics.csv` — version, year, average Jaccard, accuracy, coverage  
- `missing_annotations_fn.csv` — false negatives  
- `wrong_annotations_fp.csv` — false positives  

Plots of all metrics are automatically saved under `quality/estimates/record-dates/`.  

---

## Implementation Notes

The current reference implementation is in **`qe_meeting-dates.py`**, which:

- Merges gold-standard files  
- Extracts dates from XML protocols  
- Computes record- and protocol-level metrics  
- Generates plots per year  
- Supports parallel processing  
- Allows version tagging for reproducibility  

---

## Annotation Guidelines

1. Read the full protocol and identify all meeting dates  
2. Record them in the `docDate` column  
3. Ensure the `pdf_url` corresponds to the correct protocol  
4. Save the CSV in `quality/data/record-dates/`

---

## Example Command

```bash
python quality/qe_meeting-dates.py \
  --annotated-data quality/data/record-dates/goldstandard-dates-expert.csv \
                   quality/data/record-dates/goldstandard-dates-student.csv \
  --version v99.99.99 --show
  ```