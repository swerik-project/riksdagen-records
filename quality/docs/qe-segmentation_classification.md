# Segmentation classification error

## Summary
Each segment in the protocols belongs, according to the Parla-Clarin schema, to one type of text. This dimension estimate the proportion of correctly classified text segment.

## What is the problem
Each segment in the protocols belongs, according to the Parla-Clarin schema, to one type of text. First, we seperate the text into what is called body text (the main text that continues over pages) and margin notests (that is not part of the main text). For now, we distinguish six different segment classes.

- transcribed speech/utterance (u)
The transcription of somebody speaking in the parliament, in Swedish often called “anförande” or “yttrande”. Written speeches that are read in the parliament also fall under this, although if an  administrative matter is read out loud, then it is not an utterance. 

However, sometimes when the speaker of the house is speaking it is not always clear if there is a description or the speaker. In these cases, it should be classified as a note (see below).

- margin note (margin)
Notes in the margins of the protocols, i.e. notes that are not formatted in the text body but somewhere else on the page. Common examples are marginal notes describing the debate title,page headers, and page footers with page numbers.

- speaker introduction (intro)
The part of the protocol that introduces a new speaker by name or title, preceding a speech.

- title, header or section marker (title)
This separates the protocols into different sections within the body text (i.e. not margin notes or page headers). A title is commonly visually separated from the surrounding body text by different fonts, sizes or other visual cues.

- transcriber note (note)
Any other text that is not a transcription of somebody speaking is formatted as part of the text body. For example, decisions, descriptions of events in the parliament, and information on time.

The table of contents and decisions made in the parliaments should be classified as note. Feel free to add information on if the segment is a table of contents or decision as a comment in the annotation.


## Estimation procedure
This is a stratified simple random sample, where each segment is the sampled unit.

### Sampling plan 
To estimate segmentation classification errors, we take a stratified sample of three paragraphs per year and document type (i.e. three for each chamber) and annotate them manually.

### Annotation guidelines 
You receive a CSV file with rows that correspond to paragraphs that you will annotate. The paragraphs are ordered randomly, and there is a link to the scanned image or digital PDF. 

_Note that you should not look into the XML file where the current annotation is stored._

Each row in the CSV also has the text of that paragraph, as well as the ID of the paragraph in the XML (that will be used at the estimation stage).

Each paragraph should be classified into a category (eg. transcribed speeches or titles). See above.

If a paragraph consists of multiple different types of classes, it should be labelled with all of them. This sometimes happens when two paragraphs are accidentally merged in the XML file (i.e. due to segmentation errors).

If it is impossible to know what category the paragraph falls under, label it 'unknown'. This might be the case when the text is corrupted, or only a few words are visible.

## Other comments
It takes roughly 6-7h to classify 500 segments.

## References

