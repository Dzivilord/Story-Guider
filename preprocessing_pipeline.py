from pathlib import Path
import json, math, re, unicodedata, warnings
import numpy as np
import pandas as pd

RANDOM_STATE = 42
BASE = Path(__file__).resolve().parent
INPUT = BASE / 'data' / 'raw_data' / 'goodreads_books.parquet'
OUT = BASE / 'data' / 'processed'
OUT.mkdir(exist_ok=True)

def clean_text(x):
    if pd.isna(x): return ''
    return re.sub(r'\s+', ' ', unicodedata.normalize('NFKC', str(x))).strip()

def values(x):
    if isinstance(x, dict):
        name = x.get('name', '')
        return [clean_text(name)] if clean_text(name) else []
    if isinstance(x, (list, tuple, set, np.ndarray)):
        out = []
        for item in x:
            if isinstance(item, dict):
                item = item.get('name', '')
            item = clean_text(item)
            if item:
                out.append(item)
        return out
    if pd.isna(x): return []
    s = clean_text(x)
    if not s: return []
    try:
        y = json.loads(s.replace("'", '"'))
        if isinstance(y, list): return [clean_text(v) for v in y if clean_text(v)]
    except Exception: pass
    return [s]

def unique(seq):
    out, seen = [], set()
    for x in seq:
        k = x.casefold()
        if x and k not in seen: out.append(x); seen.add(k)
    return out

def year(x):
    if pd.isna(x): return np.nan
    m = re.search(r'(?<!\d)(1[0-9]{3}|20[0-9]{2})(?!\d)', str(x))
    if not m: return np.nan
    y = int(m.group(1)); return y if 1000 <= y <= 2100 else np.nan

def run():
    needed_columns = ['title','first_author','description','genres','series','pages','language','publication_date','average_rating','ratings_count','reviews_count','work_id','book_id','url','num_editions','is_part_of_series']
    raw = pd.read_parquet(INPUT, columns=needed_columns)
    eda = json.loads((BASE/'data'/'eda_output'/'eda_summary.json').read_text(encoding='utf-8'))
    baseline = {'rows': len(raw), 'columns': len(raw.columns), 'unique_work_id': int(raw.work_id.nunique(dropna=True)), 'unique_book_id': int(raw.book_id.nunique(dropna=True)), 'missing_work_id': int(raw.work_id.isna().sum()), 'missing_title': int(raw.title.isna().sum()), 'missing_first_author': int(raw.first_author.isna().sum()), 'missing_description': int(raw.description.isna().sum())}
    removed = []
    miss = raw[raw.work_id.isna()].copy(); removed += [{'book_id': r.get('book_id'), 'work_id': r.get('work_id'), 'reason':'missing_work_id'} for _,r in miss.iterrows()]
    original_rows = len(raw)
    df = raw[raw.work_id.notna()].copy()
    del raw
    raw = range(original_rows)  # retain input row count for the existing summary expression without retaining raw data
    for c in ['title','first_author','description']: df[c] = df[c].map(clean_text)
    df['_rating_count'] = pd.to_numeric(df.ratings_count, errors='coerce').fillna(0).clip(lower=0)
    df['_has_desc'] = df.description.ne('')
    df['_has_genres'] = df.genres.map(lambda x: bool(values(x)))
    df['_row_order'] = np.arange(len(df))
    df['_year'] = df.publication_date.map(year)
    df['_valid_pages'] = pd.to_numeric(df.pages, errors='coerce').where(lambda s: s > 0)
    # stable representative: ratings, description, genres, original order
    df = df.sort_values(['work_id','_rating_count','_has_desc','_has_genres','_row_order'], ascending=[True,False,False,False,True], kind='mergesort')
    reps = df.groupby('work_id', sort=True, dropna=False).head(1).copy().set_index('work_id')
    rows=[]; enrich_desc=0; enrich_genres=0; enrich_series=0
    for wid, g in df.groupby('work_id', sort=True):
        rep = reps.loc[wid]
        descs = sorted([x for x in g.description if x], key=lambda x: (len(x.split()), len(x)), reverse=True)
        desc = descs[0] if descs else ''
        enrich_desc += bool(desc and desc != rep.description)
        gs = unique(sum((values(x) for x in g.genres), [])); ss = unique(sum((values(x) for x in g.series), []))
        enrich_genres += bool(gs and gs != unique(values(rep.genres))); enrich_series += bool(ss and ss != unique(values(rep.series)))
        pages = g._valid_pages.median() if g._valid_pages.notna().any() else np.nan
        rows.append({'work_id':wid,'title':rep.title,'description':desc,'first_author':rep.first_author,'_raw_genres':gs,'_raw_series':ss,'pages':pages,'earliest_known_publication_year':g._year.min(),'num_editions':pd.to_numeric(g.num_editions, errors='coerce').max(),'average_rating':pd.to_numeric(rep.average_rating,errors='coerce'),'ratings_count':rep._rating_count,'reviews_count':max(0,float(pd.to_numeric(rep.reviews_count,errors='coerce') if pd.notna(rep.reviews_count) else 0)),'url':clean_text(rep.url),'language':clean_text(rep.language),'raw_is_part_of_series':bool(rep.is_part_of_series)})
    w = pd.DataFrame(rows)
    # language metadata normalization; conservative English V1 with metadata or absent metadata + substantial ASCII text
    w['language_norm'] = w.language.map(lambda x: 'English' if re.search(r'^(english|eng)(\s*;.*)?$', x, re.I) else x)
    w['_desc_english_signal'] = w.description.map(lambda x: bool(x) and len(x.split()) >= 20 and (sum(ch.isalpha() and ord(ch)<128 for ch in x)/max(1,sum(ch.isalpha() for ch in x)) >= .85))
    meta_missing = w.language_norm.eq(''); meta_eng = w.language_norm.eq('English'); noneng = w.language_norm.ne('') & ~meta_eng
    keep = meta_eng | (meta_missing & w._desc_english_signal)
    for _,r in w[~keep].iterrows(): removed.append({'work_id':r.work_id,'reason':'non_english'})
    w = w[keep].copy()
    w['_raw_tags'] = w._raw_genres.map(lambda xs: unique(xs))
    explicit = {'audiobook','audio','ebook','ebooks','kindle'}
    synonyms = {'sci fi':'Science Fiction','sci-fi':'Science Fiction','science fiction':'Science Fiction'}
    def canon_tag(x):
        k=clean_text(x).casefold(); return synonyms.get(k, clean_text(x))
    tag_counts={}
    for xs in w._raw_tags:
        for x in xs: tag_counts[canon_tag(x).casefold()] = tag_counts.get(canon_tag(x).casefold(),0)+1
    genre_rows=[]
    def clean_tags(xs):
        out=[]
        for rawx in xs:
            cx=canon_tag(rawx); k=cx.casefold(); action='merge' if cx.casefold()!=rawx.casefold() else 'keep'
            if k in explicit: action='remove'; genre_rows.append({'raw_genre':rawx,'canonical_genre':'','action':action,'reason':'format_tag'})
            elif tag_counts.get(k,0)<5: action='rare_remove'; genre_rows.append({'raw_genre':rawx,'canonical_genre':cx,'action':action,'reason':'frequency_below_5'})
            else: genre_rows.append({'raw_genre':rawx,'canonical_genre':cx,'action':action,'reason':'synonym_normalization' if action=='merge' else 'retained'}); out.append(cx)
        return unique(out)
    w['content_tags']=w._raw_tags.map(clean_tags)
    srows=[]
    def clean_series(xs):
        out=[]
        for rawx in xs:
            cx=re.sub(r'\s*(?:\(|-|–)\s*(?:chronological|publication) order\s*\)?\s*$','',rawx,flags=re.I).strip(); cx=clean_text(cx)
            srows.append({'raw_series':rawx,'canonical_series':cx,'action':'merge' if cx.casefold()!=rawx.casefold() else 'keep','reason':'ordering_suffix_removed' if cx.casefold()!=rawx.casefold() else 'retained'})
            if cx: out.append(cx)
        return unique(out)
    w['series']=w._raw_series.map(clean_series); w['is_part_of_series']=w.series.map(bool)
    w['description']=w.description.replace('',np.nan); w['has_rating']=(w.ratings_count>0) & w.average_rating.notna(); rated=w[w.has_rating]
    C=float(rated.average_rating.mean()) if len(rated) else np.nan; candidates={p:float(w.ratings_count.quantile(p)) for p in [.5,.6,.7,.75]}; m=candidates[.75]
    w['rating_confidence']=w.ratings_count/(w.ratings_count+m); w['weighted_rating']=np.where(w.has_rating,w.rating_confidence*w.average_rating+(1-w.rating_confidence)*C,np.nan)
    w['log_ratings_count']=np.log1p(w.ratings_count); w['log_reviews_count']=np.log1p(w.reviews_count); w['num_editions']=w.num_editions.fillna(1).clip(lower=1); w['log_num_editions']=np.log1p(w.num_editions)
    w['length_category']=pd.cut(w.pages,[-np.inf,200,400,600,np.inf],labels=['short','medium','long','very_long']).astype('object').fillna('unknown')
    useful_metadata = w.content_tags.map(bool) | w.first_author.ne('') | w.series.map(bool)
    bad=w.description.isna() & ~useful_metadata
    for _,r in w[bad].iterrows(): removed.append({'work_id':r.work_id,'reason':'insufficient_textual_metadata'})
    w=w[~bad].copy(); w['publication_decade']=w.earliest_known_publication_year.map(lambda x: f'{int(x)//10*10}s' if pd.notna(x) else np.nan)
    outcols=['work_id','title','description','first_author','content_tags','series','earliest_known_publication_year','publication_decade','pages','length_category','average_rating','ratings_count','reviews_count','has_rating','rating_confidence','weighted_rating','log_ratings_count','log_reviews_count','num_editions','log_num_editions','is_part_of_series','url','language']
    # Capture summary values before dropping the internal helper columns below.
    language_missing_recovered = int((meta_missing & w._desc_english_signal).sum())
    raw_genre_unique = int(len({x.casefold() for xs in w._raw_tags for x in xs}))
    raw_series_unique = int(len({x.casefold() for xs in w._raw_series for x in xs}))
    description_count = int(w.description.notna().sum())
    metadata_fallback_count = int((w.description.isna() & useful_metadata).sum())
    w=w[outcols].sort_values('work_id').reset_index(drop=True)

    # Main processed file: keep the real structured list for RecSys usage.
    w[outcols].to_parquet(OUT/'goodreads_books_processed.parquet', index=False)

    # Temporary viewer-friendly copy:
    # serialize only content_tags to JSON string so Parquet viewers show one normal column
    # instead of content_tags.list.element. The main file above is NOT changed.
    view_df = w[outcols].copy()
    view_df['content_tags'] = view_df['content_tags'].apply(
        lambda x: json.dumps(
            list(x) if isinstance(x, (list, tuple, set, np.ndarray)) else [],
            ensure_ascii=False
        )
    )
    view_df.to_parquet(OUT/'goodreads_books_processed_view.parquet', index=False)
    # Temporary compatibility fields for the existing machine-readable summary; never written to Parquet.
    w['language_norm'] = ''
    w['embedding_source'] = ''
    pd.DataFrame(removed).to_csv(OUT/'removed_records.csv',index=False); pd.DataFrame(genre_rows).drop_duplicates().sort_values(['canonical_genre','raw_genre']).to_csv(OUT/'genre_mapping.csv',index=False); pd.DataFrame(srows).drop_duplicates().sort_values(['canonical_series','raw_series']).to_csv(OUT/'series_mapping.csv',index=False)
    corr=w[['log_reviews_count','log_ratings_count']].corr(method='pearson').iloc[0,1]; spear=w[['log_reviews_count','log_ratings_count']].corr(method='spearman').iloc[0,1]
    no_desc=w.description.isna(); checks={'work_id_unique':{'status':'PASS' if w.work_id.is_unique else 'FAIL','details':{}},'title_complete':{'status':'PASS' if w.title.notna().all() else 'FAIL','details':{}},'content_tags_valid':{'status':'PASS' if w.content_tags.map(lambda x:isinstance(x,(list,tuple,np.ndarray))).all() else 'FAIL','details':{}},'series_valid':{'status':'PASS' if w.series.map(lambda x:isinstance(x,(list,tuple,np.ndarray))).all() else 'FAIL','details':{}},'ratings_valid':{'status':'PASS' if ((w.rating_confidence.between(0,1)).all() and (w.weighted_rating.dropna().between(0,5)).all()) else 'FAIL','details':{}},'pages_valid':{'status':'PASS' if (w.pages.dropna()>0).all() else 'FAIL','details':{}}}
    (OUT/'validation_report.json').write_text(json.dumps(checks,indent=2,default=str),encoding='utf-8')
    summary={'input':baseline,'work_aggregation':{'editions_removed':len(raw)-len(w),'final_unique_works':len(w),'description_enriched':enrich_desc,'genres_enriched':enrich_genres,'series_enriched':enrich_series},'language':{'works_before_filter':len(rows),'english_kept':int(keep.sum()),'non_english_removed':int((~keep).sum()),'missing_language_recovered':language_missing_recovered},'genres':{'raw_unique':raw_genre_unique,'canonical_unique':int(len({x.casefold() for xs in w.content_tags for x in xs})),'rare_removed':int(sum(r['action']=='rare_remove' for r in genre_rows))},'series':{'raw_unique':raw_series_unique,'canonical_unique':int(len({x.casefold() for xs in w.series for x in xs}))},'text_readiness':{'description':description_count,'metadata_fallback':metadata_fallback_count,'insufficient_drop':int(bad.sum())},'ratings':{'global_mean':C,'m_candidates':candidates,'chosen_m':m,'pearson_log_reviews_ratings':corr,'spearman_log_reviews_ratings':spear},'removed_records':{'total':len(removed),'by_reason':pd.DataFrame(removed).reason.value_counts().to_dict()},'final_dataset':{'rows':len(w),'columns':len(w.columns),'column_names':outcols}}
    (OUT/'preprocessing_summary.json').write_text(json.dumps(summary,indent=2,default=str),encoding='utf-8')
    summary['text_readiness']={'books_with_description':int(w.description.notna().sum()),'books_without_description':int(no_desc.sum()),'books_without_description_but_have_tags':int((no_desc & w.content_tags.map(bool)).sum()),'books_without_description_but_have_author':int((no_desc & w.first_author.ne('')).sum()),'books_without_description_but_have_series':int((no_desc & w.series.map(bool)).sum()),'books_without_description_and_no_useful_metadata':int((no_desc & ~useful_metadata).sum())}
    summary.pop('embedding_source', None)
    (OUT/'preprocessing_summary.json').write_text(json.dumps(summary,indent=2,default=str),encoding='utf-8')
    lines=['# Goodreads RecSys Preprocessing Report','',f'## Dataset Before\n- rows: {original_rows}\n- unique works: {baseline["unique_work_id"]}\n- columns: {baseline["columns"]}','',f'## Work Aggregation\n- editions removed: {original_rows-len(w)}\n- final unique works: {len(w)}\n- description enriched: {enrich_desc}\n- genres enriched: {enrich_genres}\n- series enriched: {enrich_series}','',f'## Language Filtering\n- English kept: {int(keep.sum())}\n- non-English removed: {int((~keep).sum())}','',f'## Description Availability\n- with description: {summary["text_readiness"]["books_with_description"]}\n- without description: {summary["text_readiness"]["books_without_description"]}\n- without description but with useful metadata: {len(w)-summary["text_readiness"]["books_without_description_and_no_useful_metadata"]}','',f'## Genre Cleaning\n- final unique content tags: {summary["genres"]["canonical_unique"]}\n- rare tags removed: {summary["genres"]["rare_removed"]}','',f'## Ratings\n- global mean: {C:.4f}\n- chosen m (p75 ratings_count): {m:.2f}\n- Pearson log reviews/ratings: {corr:.4f}\n- Spearman log reviews/ratings: {spear:.4f}','',f'## Final Dataset\n- rows: {len(w)}\n- columns: {len(outcols)}\n- output: `data/processed/goodreads_books_processed.parquet`']
    (OUT/'preprocessing_report.md').write_text('\n'.join(lines),encoding='utf-8')
    check=pd.read_parquet(OUT/'goodreads_books_processed.parquet')
    assert len(check)==len(w) and check.work_id.is_unique

    # Validate viewer-friendly copy and demonstrate that content_tags can be restored losslessly.
    view_check = pd.read_parquet(OUT/'goodreads_books_processed_view.parquet')
    restored_tags = view_check['content_tags'].apply(json.loads)
    assert len(view_check) == len(w)
    assert all(
        list(a) == list(b)
        for a, b in zip(restored_tags.head(100), w['content_tags'].head(100))
    )

    print('PREPROCESSING COMPLETED')
    print(f'Original editions: {original_rows}')
    print(f'Original unique works: {baseline["unique_work_id"]}')
    print(f'Final works: {len(w)}')
    print('Main file (real list): data/processed/goodreads_books_processed.parquet')
    print('Viewer file (content_tags as JSON string): data/processed/goodreads_books_processed_view.parquet')
    print(json.dumps({k:v['status'] for k,v in checks.items()}))

if __name__ == '__main__': run()
