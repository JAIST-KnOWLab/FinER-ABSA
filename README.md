# FinER-ABSA

**FinER-ABSA: A Benchmark for Implicit and Explicit Entity Recognition and Aspect-Based Sentiment Analysis in Financial News**

*Accepted at LREC 2026*

> Pachara Akkanwanich, Pavorn Thongyoo, Mahannop Thabua, Konlakorn Wongpatikaseree, Natthawut Kertkeidkachorn
>
> Mahidol University International College &bull; Mahidol University &bull; Japan Advanced Institute of Science and Technology (JAIST)

## Overview

FinER-ABSA is a benchmark dataset that integrates **implicit and explicit entity recognition** with **aspect-based sentiment analysis** in financial news. It contains 1,000 sentences sourced from Reuters Financial News, each annotated with:

- **Entity** &mdash; a publicly traded company (identified by stock ticker), either explicitly named or implicitly referenced through context
- **Aspect** &mdash; one of 36 curated financial aspect categories (e.g., Revenue, Profit, Stock Price Movement)
- **Sentiment** &mdash; fact-based polarity (Positive, Negative, or Neutral) determined by the directional implication of the event

Unlike prior benchmarks, FinER-ABSA captures **implicit entity mentions** &mdash; cases where a company is referenced through its products, executives, or market position rather than by name (e.g., *"the iPhone maker"* instead of *"Apple"*).

## Dataset Statistics

| | Count | Percentage |
|---|---:|---:|
| Explicit entities | 785 | 78.5% |
| Implicit entities | 215 | 21.5% |
| **Total sentences** | **1,000** | |

| Sentiment | Count | Percentage |
|---|---:|---:|
| Positive | 504 | 50.4% |
| Negative | 317 | 31.7% |
| Neutral | 179 | 17.9% |

- **431** unique publicly traded entities across multiple global exchanges
- **36** curated aspect categories spanning financial performance, market perception, operations, and more
- **12,808** source articles from Reuters via the Event Registry API (Jan 2014 &ndash; Oct 2024)

## Repository Structure

```
├── FINER-ABSA Dataset_sample.csv   # Main annotated dataset
├── FinER-ABSA_Expert.csv           # Expert validation labels
├── indexed_all_samples_final.xlsx  # Dataset with full article text & char indices
├── extract.py                      # Extraction pipeline (reproduces the indexed file)
├── data/
│   ├── All_Articles.xlsx           # 12,808 Reuters article bodies (Event Registry)
│   └── fetched_bodies.json         # Selenium-scraped article bodies for remaining URLs
└── README.md
```

## Files

### `FINER-ABSA Dataset_sample.csv`

The main FinER-ABSA dataset with 1,005 rows (1,000 annotated sentences + 5 negative test cases).

| Column | Description |
|---|---|
| `SID` | Unique sentence identifier (e.g., S0001) |
| `Sentence` | The annotated sentence with Reuters-specific artifacts (tickers, metadata) removed |
| `URL` | Source article URL on Reuters |
| `Entity` | The target company name |
| `Ticker` | Stock ticker symbol(s) |
| `Entity Type` | `Explicit` or `Implicit` |
| `Aspect` | One of 36 financial aspect categories |
| `Sentiment` | `Positive`, `Negative`, or `Neutral` |
| `Proof` | Keywords supporting implicit entity identification (where applicable) |

### `indexed_all_samples_final.xlsx`

Extended version of the dataset with full article text and character-level indexing. Contains all 1,005 sentences with their exact positions within the source article body.

| Column | Description |
|---|---|
| `SID` | Unique sentence identifier |
| `Sentence` | The annotated sentence (cleaned) |
| `Full_Text` | Complete article body text |
| `Char_Start` | Start character index of the sentence in `Full_Text` |
| `Char_End` | End character index of the sentence in `Full_Text` |
| `Matched_Span` | The extracted text from `Full_Text[Char_Start:Char_End]` |
| `Match_Method` | How the sentence was matched (e.g., `url+exact`, `scan+flex_word`) |
| `URL` | Source article URL |
| `Matched_Article_URL` | URL of the article where the match was found |
| `Entity` | The target company name |
| `Entity_Type` | `Explicit` or `Implicit` |
| `Aspect` | Financial aspect category |
| `Sentiment` | Sentiment label |

**Note:** `Matched_Span` may be longer than `Sentence` for `flex_word` matches, as the span captures the original article text including inline Reuters tickers (e.g., `(AAPL.O)`) and metadata that were removed during sentence cleaning.

### `data/All_Articles.xlsx`

The full corpus of 12,808 Reuters Financial News articles obtained via the Event Registry API. Contains the article body text and URL for each article.

### `data/fetched_bodies.json`

Selenium-scraped article bodies for URLs not present in `All_Articles.xlsx`. These were fetched directly from Reuters using a browser-based scraper to bypass access restrictions.

### `extract.py`

Reproduces `indexed_all_samples_final.xlsx` from the source files. Runs a two-pass matching pipeline:

1. **Pass A** &mdash; Matches sentences against the `data/All_Articles.xlsx` corpus using exact, case-insensitive, regex, and flexible word-subsequence matching.
2. **Pass B** &mdash; Matches remaining sentences against `data/fetched_bodies.json` scraped bodies, with additional Reuters-specific text cleaning.

```bash
pip install pandas openpyxl
python extract.py
```

## Benchmark Results

Seven open-weight LLMs were evaluated under zero-shot and few-shot (K=3) settings:

| Model | Entity | Aspect | Sentiment | Joint |
|---|---:|---:|---:|---:|
| Llama-3.2-3B | 0.6989 | 0.2930 | 0.2643 | 0.1290 |
| Llama-3.1-8B | 0.7375 | 0.3960 | 0.3750 | 0.1830 |
| Llama-3.3-70B | 0.7623 | 0.4792 | 0.4177 | 0.3218 |
| Qwen2.5-1.5B | 0.4435 | 0.2540 | 0.2459 | 0.0560 |
| Qwen2.5-7B-1M | 0.7518 | 0.4103 | 0.4701 | 0.1890 |
| Qwen2.5-14B-1M | 0.8405 | 0.4919 | 0.5206 | 0.2300 |
| Qwen2.5-32B | 0.8389 | 0.4856 | 0.4429 | 0.2490 |

*Few-shot (K=3) results, macro-averaged F1. "Joint" requires all three predictions to be correct simultaneously.*

On the **implicit entity subset**, even the best models achieve only 0.67&ndash;0.76 F1, roughly ten points below explicit-entity performance, confirming that implicit reasoning remains an unsolved challenge.

## Annotation Process

FinER-ABSA was annotated using a **Human-in-the-Loop (HITL)** framework:

1. **Pre-annotation** &mdash; GPT-4 Turbo generated initial labels via zero-shot prompting
2. **Human correction** &mdash; A coauthor with a finance minor reviewed and corrected all labels
3. **Expert validation** &mdash; An independent senior finance undergraduate validated annotations without access to prior labels

Inter-annotator agreement (Annotator&ndash;Expert): Cohen's &kappa; = 0.654 for aspects, 0.548 for sentiment.

## Citation

If you use FinER-ABSA in your research, please cite:

```bibtex
@inproceedings{akkanwanich2026finerabsa,
  title     = {{FinER-ABSA}: A Benchmark for Implicit and Explicit Entity Recognition and Aspect-Based Sentiment Analysis in Financial News},
  author    = {Akkanwanich, Pachara and Thongyoo, Pavorn and Thabua, Mahannop and Wongpatikaseree, Konlakorn and Kertkeidkachorn, Natthawut},
  booktitle = {Proceedings of the 2026 Joint International Conference on Computational Linguistics, Language Resources and Evaluation (LREC-COLING 2026)},
  year      = {2026}
}
```

## License

This dataset is intended solely for research and business analytics applications. It is not to be used for surveillance or any form of social governance. See the paper for full ethics statement.

## Contact

- pachara.akk@student.mahidol.edu
