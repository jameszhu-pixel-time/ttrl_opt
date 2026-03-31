# Sampled Trajectory Abnormal Group Classification

## Summary

- Abnormal groups: `24`
- `review_needed`: `8`
- `data_integrity`: `16`
- `mixed`: `0`
- `other`: `0`

## By Step

| step | review_needed | data_integrity | mixed | other |
| --- | ---: | ---: | ---: | ---: |
| 1 | 0 | 1 | 0 | 0 |
| 2 | 0 | 3 | 0 | 0 |
| 3 | 0 | 4 | 0 | 0 |
| 4 | 1 | 2 | 0 | 0 |
| 5 | 0 | 2 | 0 | 0 |
| 6 | 1 | 0 | 0 | 0 |
| 9 | 1 | 1 | 0 | 0 |
| 10 | 2 | 0 | 0 | 0 |
| 11 | 1 | 0 | 0 | 0 |
| 12 | 0 | 1 | 0 | 0 |
| 13 | 1 | 2 | 0 | 0 |
| 15 | 1 | 0 | 0 | 0 |

## Review Needed

| step | prompt_index | logged bucket | local bucket | reasons |
| --- | ---: | --- | --- | --- |
| 4 | 0 | minor | maj | bucket_changed|semantic_code_mismatch_rows_5|semantic_obj_mismatch_rows_2 |
| 6 | 22 | others | others | semantic_code_mismatch_rows_5|semantic_obj_mismatch_rows_1 |
| 9 | 22 | minor | maj | bucket_changed|semantic_code_mismatch_rows_1|semantic_obj_mismatch_rows_1 |
| 10 | 13 | minor | minor | semantic_code_mismatch_rows_1 |
| 10 | 15 | maj | maj | semantic_code_mismatch_rows_1|semantic_obj_mismatch_rows_1 |
| 11 | 21 | minor | minor | semantic_obj_mismatch_rows_1 |
| 13 | 15 | minor | minor | semantic_code_mismatch_rows_1|semantic_obj_mismatch_rows_1 |
| 15 | 10 | minor | minor | semantic_code_mismatch_rows_2|semantic_obj_mismatch_rows_1 |

## Data Integrity

| step | prompt_index | group_size | reasons |
| --- | ---: | ---: | --- |
| 1 | 22 | 32 | missing_code_rows_1 |
| 2 | 17 | 32 | missing_code_rows_1 |
| 2 | 19 | 64 | group_size_64|missing_code_rows_1 |
| 2 | 21 | 32 | missing_code_rows_1 |
| 3 | 2 | 32 | missing_code_rows_1 |
| 3 | 8 | 32 | missing_code_rows_1 |
| 3 | 15 | 32 | missing_code_rows_1 |
| 3 | 31 | 32 | missing_code_rows_1 |
| 4 | 4 | 32 | missing_code_rows_1 |
| 4 | 28 | 32 | missing_code_rows_1 |
| 5 | 12 | 32 | missing_code_rows_1 |
| 5 | 19 | 32 | missing_code_rows_1 |
| 9 | 12 | 32 | missing_code_rows_1 |
| 12 | 22 | 32 | missing_code_rows_1 |
| 13 | 24 | 32 | missing_code_rows_1 |
| 13 | 29 | 64 | group_size_64 |
