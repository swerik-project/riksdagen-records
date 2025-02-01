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
annotation information, record name and page number.

### Sampling plan
A random sample of three pages per 5-year period and chamber is draws. 
The final estimate will be a stratified random sample.

### Annotation guidelines
The annotator read check the records and manually extract all meeting dates for each record into a CSV file.
1. Write down the first full sentence in the body text.
2. Write down the page number of page name of the page (e.g. roman numbers)
