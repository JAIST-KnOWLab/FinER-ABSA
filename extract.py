"""
FinER-ABSA sentence extraction pipeline.

Matches each sample sentence to its source article body and records
character-level indices. Combines two passes:

  Pass A – Match against the All_Articles.xlsx corpus (Event Registry bodies).
  Pass B – Match remaining sentences against Selenium-scraped bodies
           cached in fetched_bodies.json (Reuters pages fetched via browser).

Output: indexed_all_samples_final_v2.xlsx with all matched rows.
"""

import re
import json
from collections import defaultdict
from pathlib import Path

import pandas as pd

# ── file paths ──────────────────────────────────────────────────────────────
SAMPLES_CSV       = "FINER-ABSA Dataset_sample.csv"
EXPERT_CSV        = "FinER-ABSA_Expert.csv"
ALL_ARTICLES_XLSX = "data/All_Articles.xlsx"
FETCHED_BODIES    = "data/fetched_bodies.json"
FINISHED_MATCHED  = Path(r"C:\Users\pthongyoo\Downloads\Finished matched.xlsx")
OUTPUT_FILE       = "indexed_all_samples_final.xlsx"


# ═══════════════════════════════════════════════════════════════════════════
# Text utilities
# ═══════════════════════════════════════════════════════════════════════════

def norm(text):
    t = str(text)
    for a, b in {
        '\u00a0': ' ', '\u2019': "'", '\u2018': "'",
        '\u201c': '"', '\u201d': '"', '\u2014': '-',
        '\u2013': '-', '\u2026': '...', '\ufeff': '',
        '\u200b': '', '\xa0': ' ',
    }.items():
        t = t.replace(a, b)
    return re.sub(r'\s+', ' ', t).strip()


def tokenize(text):
    """Return (normalised_lower_word, char_start, char_end) tuples."""
    return [(norm(m.group()).lower(), m.start(), m.end())
            for m in re.finditer(r"\w+(?:['\u2019\u2018]\w+)*", text)]


def clean_reuters_body(text):
    """Strip inline ticker symbols and 'opens new tab' from rendered Reuters text."""
    t = text
    t = re.sub(r'\s*\([A-Za-z0-9]+\.[A-Za-z0-9]+\)\s*,?\s*(?:opens new tab)?\s*', ' ', t, flags=re.IGNORECASE)
    t = re.sub(r',?\s*opens new tab\s*', ' ', t, flags=re.IGNORECASE)
    t = re.sub(r',?\s*New Tab\s*', ' ', t)
    t = re.sub(r' +([,\.;:!?])', r'\1', t)
    t = re.sub(r' {2,}', ' ', t)
    t = re.sub(r'\n\s*\n', '\n', t)
    return t.strip()


# ═══════════════════════════════════════════════════════════════════════════
# Matching functions
# ═══════════════════════════════════════════════════════════════════════════

def try_exact_family(sent, body_raw):
    idx = body_raw.find(sent)
    if idx >= 0:
        return (idx, idx + len(sent), 'exact')
    idx = body_raw.lower().find(sent.lower())
    if idx >= 0:
        return (idx, idx + len(sent), 'icase')
    ns = norm(sent)
    nb = norm(body_raw)
    idx = nb.find(ns)
    if idx >= 0:
        return (idx, idx + len(ns), 'norm_exact')
    idx = nb.lower().find(ns.lower())
    if idx >= 0:
        return (idx, idx + len(ns), 'norm_icase')
    try:
        pat = re.escape(ns).replace(r'\ ', r'\s+')
        m = re.search(pat, body_raw, re.IGNORECASE)
        if m:
            return (m.start(), m.end(), 'regex_ws')
    except Exception:
        pass
    return None


def flexible_word_match(sent, body_raw, body_tokens=None, max_gap=5):
    """Match sentence words as a subsequence of body words, allowing
    up to max_gap extra words (tickers, 'opens new tab', etc.) between
    each pair. Returns span from first matched word to last, extended to
    capture trailing punctuation."""
    sent_tokens = tokenize(norm(sent))
    if body_tokens is None:
        body_tokens = tokenize(body_raw)
    if not sent_tokens or not body_tokens:
        return None
    n_sent = len(sent_tokens)
    first_word = sent_tokens[0][0]

    for start_bi in range(len(body_tokens)):
        if body_tokens[start_bi][0] != first_word:
            continue
        si = 1
        bi = start_bi + 1
        gap = 0
        while si < n_sent and bi < len(body_tokens):
            if body_tokens[bi][0] == sent_tokens[si][0]:
                si += 1
                gap = 0
            else:
                gap += 1
                if gap > max_gap:
                    break
            bi += 1
        if si >= n_sent:
            char_start = body_tokens[start_bi][1]
            char_end = body_tokens[bi - 1][2]
            while char_end < len(body_raw) and body_raw[char_end] in '.,:;!?\'")"':
                char_end += 1
            return (char_start, char_end, 'flex_word')
    return None


def match_in_body(sent, body_raw, body_tokens=None):
    r = try_exact_family(sent, body_raw)
    if r:
        return r
    return flexible_word_match(sent, body_raw, body_tokens=body_tokens)


def manual_regex_match(sent, body_raw):
    """Last-resort matcher: allow non-letter chars (or nothing) between words."""
    words = re.findall(r'\w+', sent)
    if not words:
        return None
    pattern = r'[^a-zA-Z]*'.join(re.escape(w) for w in words)
    m = re.search(pattern, body_raw, re.IGNORECASE)
    if m:
        char_end = m.end()
        while char_end < len(body_raw) and body_raw[char_end] in '.,:;!?\'")"':
            char_end += 1
        return (m.start(), char_end, 'manual_regex')
    return None


# ═══════════════════════════════════════════════════════════════════════════
# Load data
# ═══════════════════════════════════════════════════════════════════════════

print("Loading data...")
samples = pd.read_csv(SAMPLES_CSV)
all_articles = pd.read_excel(ALL_ARTICLES_XLSX)
expert = pd.read_csv(EXPERT_CSV)

samples_merged = samples.merge(
    expert[['SID', 'Ticker']].drop_duplicates('SID'),
    on='SID', how='left',
)
sc = samples_merged.dropna(subset=['Sentence']).reset_index(drop=True)

# ═══════════════════════════════════════════════════════════════════════════
# Pass A – Match against All_Articles.xlsx bodies
# ═══════════════════════════════════════════════════════════════════════════

print("Pre-tokenizing article bodies...")
body_cache = []
for _, art in all_articles.iterrows():
    raw = str(art.get('body', ''))
    if len(raw) < 30 or raw == 'nan':
        body_cache.append(None)
        continue
    raw_tokens = tokenize(raw)
    body_cache.append({
        'raw': raw,
        'norm': norm(raw),
        'url': str(art.get('url', '')),
        'tokens': raw_tokens,
        'word_set': set(t[0] for t in raw_tokens if len(t[0]) >= 3),
    })
print(f"  Cached {sum(1 for b in body_cache if b)} article bodies")

url_idx = {}
for i, art in all_articles.iterrows():
    k = str(art['url']).strip().lower().rstrip('/').split('#')[0].split('?')[0].rstrip('/')
    url_idx.setdefault(k, i)

results = []
stats = defaultdict(int)
missed_sids = set()
missed = []

print("\n=== Pass A: matching against All_Articles corpus ===")
for i, row in sc.iterrows():
    if i % 200 == 0:
        print(f"  [{i}/{len(sc)}] matched: {len(results)}")
    sent = str(row['Sentence']).strip()
    url = str(row.get('URL', '')).strip()
    url = '' if url == 'nan' else url
    sid = row['SID']
    matched = False
    url_exists = False

    def save(body_info, s, e, method):
        matched_article_url = str(body_info.get('url', '')).strip()
        final_url = url if url else matched_article_url
        results.append({
            'SID': sid, 'Sentence': sent, 'Full_Text': body_info['raw'],
            'Char_Start': s, 'Char_End': e,
            'Matched_Span': body_info['raw'][s:e],
            'Match_Method': method,
            'URL': final_url,
            'Matched_Article_URL': matched_article_url,
            'Entity': row.get('Entity', ''),
            'Entity_Type': row.get('Entity Type', ''),
            'Aspect': row.get('Aspect', ''),
            'Sentiment': row.get('Sentiment', ''),
        })

    if url:
        ukey = url.lower().rstrip('/').split('#')[0].split('?')[0].rstrip('/')
        bi = url_idx.get(ukey)
        if bi is not None and body_cache[bi]:
            url_exists = True
            r = match_in_body(sent, body_cache[bi]['raw'], body_tokens=body_cache[bi]['tokens'])
            if r:
                save(body_cache[bi], r[0], r[1], f'url+{r[2]}')
                stats[f'url+{r[2]}'] += 1
                matched = True

    if not matched:
        sent_words = set(t[0] for t in tokenize(norm(sent)) if len(t[0]) >= 4)
        need = max(3, int(len(sent_words) * 0.5))
        for bi, binfo in enumerate(body_cache):
            if binfo is None:
                continue
            if len(sent_words & binfo['word_set']) < need:
                continue
            r = match_in_body(sent, binfo['raw'], body_tokens=binfo['tokens'])
            if r:
                save(binfo, r[0], r[1], f'scan+{r[2]}')
                stats[f'scan+{r[2]}'] += 1
                matched = True
                break

    if not matched:
        stats['pass_a_unmatched'] += 1
        missed_sids.add(sid)
        missed.append({
            'SID': sid,
            'Sample_Sentence': sent,
            'URL': url,
            'URL_exists': url_exists,
        })

pass_a_matched = len(results)
print(f"\n  Pass A matched: {pass_a_matched} / {len(sc)}")
print(f"  Pass A unmatched: {len(missed_sids)}")

# ═══════════════════════════════════════════════════════════════════════════
# Pass B – Match remaining sentences against Selenium-scraped bodies
# ═══════════════════════════════════════════════════════════════════════════

pass_b_matched = 0

if missed_sids and Path(FETCHED_BODIES).exists():
    print("\n=== Pass B: matching unmatched against scraped bodies ===")
    with open(FETCHED_BODIES, 'r', encoding='utf-8') as f:
        url_bodies = json.load(f)
    print(f"  Loaded {len(url_bodies)} scraped bodies")

    if FINISHED_MATCHED.exists():
        fm = pd.read_excel(FINISHED_MATCHED)
        fm = fm.merge(
            samples[['SID', 'Entity', 'Entity Type', 'Aspect', 'Sentiment']].drop_duplicates('SID'),
            on='SID', how='left',
        )
    else:
        fm = sc[sc['SID'].isin(missed_sids)].copy()
        fm['Sample_Sentence'] = fm['Sentence']

    for _, row in fm.iterrows():
        sid = row['SID']
        if sid not in missed_sids:
            continue
        sent = str(row.get('Sample_Sentence', row.get('Sentence', ''))).strip()
        url = str(row.get('URL', '')).strip()
        raw_body = url_bodies.get(url, '')

        if not raw_body or len(raw_body) < 30:
            continue

        # Try cleaned body first, then raw, then aggressively cleaned
        cleaned = clean_reuters_body(raw_body)
        r = match_in_body(sent, cleaned)
        if r:
            body = cleaned
        else:
            r = match_in_body(sent, raw_body)
            body = raw_body

        if not r:
            spaced = re.sub(r'([a-z])([A-Z$])', r'\1 \2', raw_body)
            spaced = re.sub(r'(\w)([$])', r'\1 \2', spaced)
            spaced = clean_reuters_body(spaced)
            r = match_in_body(sent, spaced)
            if r:
                body = spaced

        if not r:
            r = manual_regex_match(sent, cleaned)
            if r:
                body = cleaned

        if not r:
            r = manual_regex_match(sent, raw_body)
            if r:
                body = raw_body

        if r:
            results.append({
                'SID': sid,
                'Sentence': sent,
                'Full_Text': body,
                'Char_Start': r[0],
                'Char_End': r[1],
                'Matched_Span': body[r[0]:r[1]],
                'Match_Method': f'selenium+{r[2]}',
                'URL': url,
                'Matched_Article_URL': url,
                'Entity': row.get('Entity', ''),
                'Entity_Type': row.get('Entity Type', ''),
                'Aspect': row.get('Aspect', ''),
                'Sentiment': row.get('Sentiment', ''),
            })
            missed_sids.discard(sid)
            stats[f'selenium+{r[2]}'] += 1
            pass_b_matched += 1

    print(f"  Pass B matched: {pass_b_matched}")
    print(f"  Still unmatched: {len(missed_sids)}")
elif missed_sids:
    print(f"\n  Skipping Pass B ({FETCHED_BODIES} not found)")

# ═══════════════════════════════════════════════════════════════════════════
# Summary & output
# ═══════════════════════════════════════════════════════════════════════════

total = len(sc)
matched = len(results)

print()
print('=' * 60)
print(f'  Total samples:           {total}')
print(f'  Matched (Pass A):        {pass_a_matched}')
print(f'  Matched (Pass B):        {pass_b_matched}')
print(f'  Total matched:           {matched}')
print(f'  Still unmatched:         {total - matched}')
print(f'  Success rate:            {matched/total*100:.1f}%')
print('=' * 60)
print()
print('By method:')
for k, v in sorted(stats.items(), key=lambda x: -x[1]):
    print(f'  {k:30s} {v:>5}')

if missed_sids:
    print(f'\nStill unmatched SIDs:')
    for m in [x for x in missed if x['SID'] in missed_sids]:
        print(f"  {m['SID']}: {m['Sample_Sentence'][:100]}...")

output_df = pd.DataFrame(results).sort_values('SID').reset_index(drop=True)
output_df.to_excel(OUTPUT_FILE, index=False)
print(f"\nSaved {len(output_df)} rows to {OUTPUT_FILE}")

# Verification
print("\nVerifying a few flex_word matches:")
flex_rows = output_df[output_df['Match_Method'].str.contains('flex_word', na=False)].head(5)
for _, r in flex_rows.iterrows():
    print(f"  {r['SID']} ({r['Match_Method']})")
    print(f"    Sentence: {r['Sentence'][:120]}")
    print(f"    Span:     {r['Matched_Span'][:200]}")
    print()
