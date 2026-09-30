# Goodreads RecSys Preprocessing Report

## Dataset Before
- rows: 205000
- unique works: 196377
- columns: 16

## Work Aggregation
- editions removed: 40133
- final unique works: 164867
- description enriched: 2791
- genres enriched: 39
- series enriched: 0

## Language Filtering
- English kept: 164873
- non-English removed: 31504

## Description Availability
- with description: 144707
- without description: 20160
- without description but with useful metadata: 164865

## Genre Cleaning
- final unique content tags: 942
- rare tags removed: 580

## Ratings
- global mean: 3.8372
- chosen m (p75 ratings_count): 34.00
- Pearson log reviews/ratings: 0.9505
- Spearman log reviews/ratings: 0.8731

## Final Dataset
- rows: 164867
- columns: 23
- output: `data/processed/goodreads_books_processed.parquet`
