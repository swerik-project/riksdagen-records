# Meeting dates quality estimation

## Summary
We want to know the proportion of meeting dates that is correct in the corpus

## What is the problem
We want to estimate the proportion and Jaccard index of the records that has correct meeting dates. 
These dates are important for the Riksdag library to extract the right records by time periods.

## Estimation procedure
A stratified random sample is manually annotated by experts at the library. 
Then these annotations are compared with the dates extracted. This file is stored under quality/data/meeting_dates.csv.

### Sampling plan
A random sample of three records per year and chamber has been created. 
The final estimate will be a stratified random sample.

### Annotation guidelines
The annotator read check the records and manually extract all meeting dates for each record into a CSV file.

