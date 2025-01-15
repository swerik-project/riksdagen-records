# Riksdagen Records: Quality Estimation

This directory contains code and data related to estimating the quality of the Riksdagen records corpus, along with the estimates themselves.

## What's here?

### `./`

Python code used to estimate various quality dimensions.

- `qe_ocr-estimation.py` : Estimates OCR quality
- `qe_segment-classification.py` : Estimates segment classification quality
- `qe_speaker-mapping-accuracy.py` : Estimates quality of speech-speaker mapping, tagged speaker is correct speaker
- `qe_speaker-mapping-coverage.py` : Estimates the coverage of speaker mapping, known vs unknown


Support files

- `README.md` : this file
- `__init__.py` : used for building the documentation


### `data/`

Contains data necessary to run the quality estimation code.


### `docs/`

Contains explanation and justifications for each quality dimension.


### `estimates/`

Contains versioned output of quality estimations.
