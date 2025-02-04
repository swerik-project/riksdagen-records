# Page link and number quality estimation

## Summary
We want to know the proportion of links to original pages and the page numbers that are correct.

## What is the problem
In the corpus, information with links to the original pages are included. 
Some of these might either be incorrect or incorrect page numbering.
We want to estimate the proportion of correct links.

## Estimation procedure
A stratified random sample of pages are manually annotated. 
For each randomly sampled page the page number/name and the first sentence in the body text.
Then these annotations are compared with the links and page number/name extracted.
This file is stored under quality/data/page_number_links.csv and contain the 
annotation information, record name and page link (the link to the individual page as stored in the pdf repository).

### Sampling plan
A random sample of three pages per 5-year (e.g. 1867-1869, 1870-1874, 1875-1879, ...) period and chamber. 
The final estimate will be a stratified random sample.

### Annotation guidelines
The annotator read check the records and manually extract information from each record page into a CSV file.
1. Write down the first full sentence in the body text.
2. Write down the page number (i.e. the page number of the page as written in the original document, e.g. roman numbers)
