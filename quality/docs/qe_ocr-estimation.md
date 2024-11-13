# Optical Character Recognition (OCR) error

## Summary

The goal is to estimate the total OCR error in the corpus. The quality of the OCR might differ between different years and between different documents. Hence, we take a stratified sample by year and document.


## What is the problem

In this quality dimension we want to estimate the total OCR error in the corpus, as can be described as the textual representation error in [Hurtado Bodell, Magnusson & Müntzel (2022)](https://raw.githubusercontent.com/swerik-project/swerik-reference-list/refs/heads/main/bibfiles/HurtadoBodellMagnussonMutzel2022.bib). The quality of the OCR is important in many research applications that rely on the text being correct.


## Estimation procedure

This is a stratified cluster sample, where the page is the cluster and the strata are years and document.


### Sampling plan 

We take a stratified sample of two pages per year and document type. Then on each page, the annotator counts the number of rows in the body text, writes down the number of rows and takes a random sample of three rows. 

If there are two columns, count each row in each column as a separate row but double the sample size (to six rows), i.e. we sample three full lines per document.


### Annotation guidelines 

Annotators receive a CSV with the page and a link to the page with three rows per page.

- Start by counting the total number of rows (or row-column combinations) of the main text (ignore marginal notes). Add the total number of rows under the NROWS column
- Then sample three rows (or six rows if the page is two columns) and indicate the sampled row in the csv.
- Write down the row line and the content of these three lines in the csv-file (one row per line) in order (ie the first row first).


## Other comments

The quality data has been annotated by students at Uppsala University.


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
