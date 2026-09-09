# Debate Header Quality

## Summary

Each debate in the parliamentary protocols should include a *debate header* that accurately captures the debate's topic and supports navigation, search, and downstream tasks. We should check how often these titles are correctly included in the corpus.

## What is the problem
Headers are often of insufficient quality. Typical problems include:

- **Missing titles:** no title is provided for a debate where one should exist.
- **Truncated / noisy titles:** OCR artefacts, incomplete strings, or formatting fragments that do not form a meaningful title.
- **Definition of header:** it is not always clear what counts as a “debate header” (e.g., is a margin note sufficient? Does it need to be in the body text? Should we include all headers?). We need a clear definition to ensure consistent annotation across time.

A reliable estimate of these issues is needed before we invest in systematic improvement.

## Definition

A **debate header title** is the short textual label in the body text that identifies *what item the following speeches belong to*. It is usually a visible heading, and it should be interpretable without additional context.

A header candidate is a text element that satisfies all of these:

1. Visually separated from body text
It stands alone on its own line(s), or has extra whitespace around it, or is typographically distinct (bigger font, bold, caps, centred, etc.).

2. Has a structural role (labels the next block)
It signals “what comes next”: a debate item/topic/section.

3. Not a speech line or introduction to a speech.
It’s not a speaker cue like “Anf.” / “Herr/Fru X:” / “TALMANNEN:” or similar.

4. Is followed by a block of speeches.
Note that only headers that are visually separated and have a structural role are counted. For example, if there is a line of text that is not visually distinct but happens to be the first line of a debate item, it would not count as a header. Similarly, if there is a visually distinct line that does not label the next block of speeches, it would not count as a debate header.

5. The title should divide the body text into separate sections, i.e. there is often body text both before and after the header.

6. Bold text alone is not enough for a text element to count as a debate header. It must also label the handled item that follows.

7. Titles in figures, tables, and similar are not headers.

### Annotation clarifications

Document-level headings are not debate headers. For example, first-page headings such as "RIKSDAGENS PROTOKOLL. 1882. Andra Kammaren. N:o 52" identify the protocol as a whole, not the item handled in the following debate. These should not be annotated as debate headers.

Margin notes, page headers, and page footers are not debate headers. They may describe the topic of the page or help navigation, but they are not part of the body text that divides the protocol into handled items.

When a matter is introduced by a protocol paragraph, such as "§ 25", annotate that paragraph heading if it starts the handled item. Do not annotate legal paragraphs or sections that are only quoted, amended, or discussed within that matter, such as references to "§ 14" or "§ 17" under "§ 25".

If a paragraph marker appears out of sequence or as part of a list of points handled within an already introduced matter, it is not a new debate header. Annotate it only if it clearly starts a new handled item and labels the following body text.

If the same paragraph heading or title is repeated because a matter continues across pages or because of page layout, do not count the repetition as a new debate header. Annotate repeated wording only when it clearly starts a distinct new handled item.

When a protocol paragraph marker is followed by a visually separated descriptive title, for example a paragraph number followed by a bold line, annotate the paragraph marker and the descriptive title together as one debate header.

If only part of a heading line is typographically distinct, for example only the paragraph marker is bold, annotate the full heading line if the whole line labels the handled item.

Annotate bold text only if it is visually separated from the body text and labels the handled item that follows. Do not annotate bold text that is only emphasis, quoted text, or part of an already introduced matter.

Table of contents headings, such as "Innehållsförteckning", are not debate headers. They help navigate the document, but they do not introduce a handled item followed by speeches.

We evaluate debate titles on the core property:
**Correctness:** Does the XML contain the same number of debate titles on the sampled page as the expert annotation, and do the title texts match?

For this estimate, title text is normalized before comparison. Normalization means that Unicode is standardized, whitespace runs are collapsed to a single space, case is ignored, and trailing punctuation such as `.`, `;`, `:`, `,`, and `-` is ignored. A small number of character-level differences is allowed after normalization to avoid counting minor OCR artefacts as errors: the edit distance may be at most one character, or about 5 percent of the longer normalized title, whichever is larger.

## Scope

- Start with **Enkammarriksdagen** (unicameral period) to measure annotation time and get a first estimate.
- After timing and initial results, optionally extend further back (bicameral) 


## Estimation procedure

This is a simple random sample in which a page is the sampling unit, and the annotator should assess whether a header is present on the page. For each sampled page, the annotator reviews the scanned page or PDF and assesses the header title. If one exists, it should be written down (or copied from the XML).

### Sampling plan

- Draw a random sample of 3 pages per year from the unicameral period.

## Annotation guidelines

You receive a CSV with one row per sampled debate, containing at a minimum:

- `page_id` (stable identifier)
- link to scanned page(s) or PDF
- link to XML file
- text of the header (if any)

For each row:

1) Open the scan/PDF (do **not** inspect the XML).  
2) Identify if there is a heading and write it down in the CSV file. If multiple headers, separate them by semicolon (;). Here the XML can be used to copy (and correct) the text. If there is no title, just mark "[no header]".

## Other comments
