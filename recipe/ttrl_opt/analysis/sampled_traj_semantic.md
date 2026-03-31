# Sampled Trajectory Semantic Report

## Overall

- Steps: `18`
- Rows: `18432`
- Prompt groups: `574`
- Abnormal groups: `24`
- Logged buckets: `maj=465, minor=68, others=41`
- Local buckets: `maj=467, minor=66, others=41`
- Strict code mismatches: `349`
- Semantic code mismatches: `16`
- Semantic objective mismatches: `8`
- Missing-key rows: `0`
- Invalid-json rows: `0`

## Per-Step

| step | prompt groups | abnormal groups | logged dist | local dist | semantic code mismatch rows | semantic obj mismatch rows |
| --- | ---: | ---: | --- | --- | ---: | ---: |
| 1 | 32 | 1 | 29/3/0 | 29/3/0 | 0 | 0 |
| 2 | 31 | 3 | 23/4/4 | 23/4/4 | 0 | 0 |
| 3 | 32 | 4 | 24/5/3 | 24/5/3 | 0 | 0 |
| 4 | 32 | 3 | 28/1/3 | 29/0/3 | 5 | 2 |
| 5 | 32 | 2 | 26/5/1 | 26/5/1 | 0 | 0 |
| 6 | 32 | 1 | 24/3/5 | 24/3/5 | 5 | 1 |
| 7 | 32 | 0 | 25/4/3 | 25/4/3 | 0 | 0 |
| 8 | 32 | 0 | 25/3/4 | 25/3/4 | 0 | 0 |
| 9 | 32 | 2 | 24/5/3 | 25/4/3 | 1 | 1 |
| 10 | 32 | 2 | 28/3/1 | 28/3/1 | 2 | 1 |
| 11 | 32 | 1 | 27/4/1 | 27/4/1 | 0 | 1 |
| 12 | 32 | 1 | 28/2/2 | 28/2/2 | 0 | 0 |
| 13 | 31 | 3 | 23/6/2 | 23/6/2 | 1 | 1 |
| 14 | 32 | 0 | 26/5/1 | 26/5/1 | 0 | 0 |
| 15 | 32 | 1 | 24/7/1 | 24/7/1 | 2 | 1 |
| 16 | 32 | 0 | 25/4/3 | 25/4/3 | 0 | 0 |
| 17 | 32 | 0 | 29/2/1 | 29/2/1 | 0 | 0 |
| 18 | 32 | 0 | 27/2/3 | 27/2/3 | 0 | 0 |

## Abnormal Groups

| step | prompt_index | group_size | logged bucket | local bucket | reasons |
| --- | ---: | ---: | --- | --- | --- |
| 1 | 22 | 32 | maj | maj | missing_code_rows_1 |
| 2 | 17 | 32 | maj | maj | missing_code_rows_1 |
| 2 | 19 | 64 | maj | maj | group_size_64|missing_code_rows_1 |
| 2 | 21 | 32 | others | others | missing_code_rows_1 |
| 3 | 2 | 32 | others | others | missing_code_rows_1 |
| 3 | 8 | 32 | maj | maj | missing_code_rows_1 |
| 3 | 15 | 32 | maj | maj | missing_code_rows_1 |
| 3 | 31 | 32 | maj | maj | missing_code_rows_1 |
| 4 | 0 | 32 | minor | maj | bucket_changed|semantic_code_mismatch_rows_5|semantic_obj_mismatch_rows_2 |
| 4 | 4 | 32 | maj | maj | missing_code_rows_1 |
| 4 | 28 | 32 | maj | maj | missing_code_rows_1 |
| 5 | 12 | 32 | others | others | missing_code_rows_1 |
| 5 | 19 | 32 | maj | maj | missing_code_rows_1 |
| 6 | 22 | 32 | others | others | semantic_code_mismatch_rows_5|semantic_obj_mismatch_rows_1 |
| 9 | 12 | 32 | maj | maj | missing_code_rows_1 |
| 9 | 22 | 32 | minor | maj | bucket_changed|semantic_code_mismatch_rows_1|semantic_obj_mismatch_rows_1 |
| 10 | 13 | 32 | minor | minor | semantic_code_mismatch_rows_1 |
| 10 | 15 | 32 | maj | maj | semantic_code_mismatch_rows_1|semantic_obj_mismatch_rows_1 |
| 11 | 21 | 32 | minor | minor | semantic_obj_mismatch_rows_1 |
| 12 | 22 | 32 | maj | maj | missing_code_rows_1 |
| 13 | 15 | 32 | minor | minor | semantic_code_mismatch_rows_1|semantic_obj_mismatch_rows_1 |
| 13 | 24 | 32 | maj | maj | missing_code_rows_1 |
| 13 | 29 | 64 | maj | maj | group_size_64 |
| 15 | 10 | 32 | minor | minor | semantic_code_mismatch_rows_2|semantic_obj_mismatch_rows_1 |
