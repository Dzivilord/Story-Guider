# Goodreads processed data — presentation extract

- Source: `data/processed/goodreads_books_processed.parquet`
- Full dataset rows: 164,867
- Columns: 23
- Sample rows: 10

## Schema

| Column | Type | Non-null | Null |
|---|---:|---:|---:|
| `work_id` | `float64` | 164,867 | 0 |
| `title` | `str` | 164,867 | 0 |
| `description` | `str` | 144,707 | 20,160 |
| `first_author` | `str` | 164,867 | 0 |
| `content_tags` | `str` | 164,867 | 0 |
| `series` | `object` | 164,867 | 0 |
| `earliest_known_publication_year` | `float64` | 155,983 | 8,884 |
| `publication_decade` | `str` | 155,983 | 8,884 |
| `pages` | `float64` | 141,316 | 23,551 |
| `length_category` | `str` | 164,867 | 0 |
| `average_rating` | `float64` | 164,867 | 0 |
| `ratings_count` | `float64` | 164,867 | 0 |
| `reviews_count` | `float64` | 164,867 | 0 |
| `has_rating` | `bool` | 164,867 | 0 |
| `rating_confidence` | `float64` | 164,867 | 0 |
| `weighted_rating` | `float64` | 115,148 | 49,719 |
| `log_ratings_count` | `float64` | 164,867 | 0 |
| `log_reviews_count` | `float64` | 164,867 | 0 |
| `num_editions` | `float64` | 164,867 | 0 |
| `log_num_editions` | `float64` | 164,867 | 0 |
| `is_part_of_series` | `bool` | 164,867 | 0 |
| `url` | `str` | 164,867 | 0 |
| `language` | `str` | 164,867 | 0 |

## Sample

See `goodreads_books_processed_sample.csv` for 10 sample records.
