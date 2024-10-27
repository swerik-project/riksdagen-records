# Optical Character Recognition (OCR) error

## Summary
The goal is to estimate the total OCR error in the corpus. The quality of the OCR might differ between different years and between different documents. Hence, we take a stratified sample by year and document.

## What is the problem
In this quality dimension we want to estimate the total OCR error in the corpus, as can be described as the textual representation error in Hurtado Bodell et al (2022). The quality of the OCR is important in many research applications that rely on the text being correct.

## Estimation procedure
This is a stratified cluster sample, where the page is the cluster and the strata are years and document.

### Sampling plan 
We take a stratified sample of two pages per year and document type. Then on each page, the annotator counts the number of rows in the body text, writes down the number of rows and takes a random sample of three rows. 

If there are two columns, count each row in each column as a separate row but double the sample size (to six rows), i.e. we sample three full lines per document.

### Annotation guidelines 
You will get a CSV with the page and a link to the page with three rows per page.
- Start by counting the total number of rows (or row-column combinations) of the main text (ignore marginal notes). Add the total number of rows under the NROWS column
- Then sample three (or six if two columns) rows and indicate the sampled row in the csv.
- Write down the row line and the content of these three lines in the csv-file (one row per line) in order (ie the first row first).


## Other comments
The quality data has been annotated by students at Uppsala University.


## References
Hurtado Bodell, M., Magnusson, M., & Mützel, S. (2022). From Documents to Data: A Framework for Total Corpus Quality. Socius, 8.

