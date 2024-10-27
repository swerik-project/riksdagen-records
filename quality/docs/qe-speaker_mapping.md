# Speaker mapping error

## Summary
Each speech in the parliament is mapped to a member of parliament, and each speech is introduced in an introduction segment. We are interested in knowing the quality of the mapping between the speech and the true member of parliament.

## What is the problem
In this quality dimension we want to estimate the proportion of the maps to speakers that are correct. The quality of the mapping is important when there is an interest in the analysis of speeches by member of parliament.

## Estimation procedure
This is a stratified simple random sample, where each introduction is the sampled unit.

### Sampling plan 
To estimate the MP mapping errors, we take a stratified sample of three introductions per year and document type (i.e. three introductions per chamber) and annotate them by the true ID.

### Annotation guidelines 
You will get a CSV with the introduction text, a link to the PDF/image of the page, and the paragraph id (that is used later on). 

The introduction might look something like this

>Herr Anderson i Stockholm (s):

You should try and find a matching person on Wikidata (name, party, i-ort, time period, gender, chamber, etc.). Then you add the Wikidata identifier in the 'speaker' column.

If it is impossible to find the person, add 'unknown' in the speaker column for that introduction.


## Other comments


## References

