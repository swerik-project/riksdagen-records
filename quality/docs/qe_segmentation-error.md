# (planned) Segmentation error

This quality dimension is not yet implemented.

## Summary
Each segment in the protocols belongs, according to the Parla-Clarin schema, to one segment. This dimension estimate the quality of the segmentation.

## What is the problem
Segmentation is the property of the text of the documents being correctly split into different text segments. Each page should be segmented into paragraphs and split if there is a difference in segmentation class (see below).

Two types of errors can occur that are of interest to estimate. Either a segmentation point is wrong (and should be removed), or a segmentation is missing at a specific position.

## Estimation procedure
This is a stratified simple random sample, where each page is the sampled unit.

### Sampling plan 
To estimate segmentation error, a stratified sample of two pages per year and document type are sampled.

### Annotation guidelines 
You will get a page and a text file for that page, together with the page before and after. The text will only be a stream of text.

Start by insert page breaks <pb> to segment the sampled page. The insert the segmentation points as <sp> in the text file where there should be segmentation point in the document. What segment classes the different segments contains is less relevant here and does not need to be annotated.

## Other comments


## References

