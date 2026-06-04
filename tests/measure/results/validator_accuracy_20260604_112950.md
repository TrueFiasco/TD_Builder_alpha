# measure — validator_accuracy (2026-06-04T11:29:50+00:00)

**score_mean = 0.6667**  (n=9)
Δ vs baseline @2026-06-04T10:04:13+00:00: +0.0000

## metrics

- false_flag: 0.0000  (Δ +0.0000)
- miss: 0.5000  (Δ +0.0000)
- false_flag_rate: 0.0000  (Δ +0.0000)
- miss_rate: 0.5000  (Δ +0.0000)
- right_stage_rate: 0.5000  (Δ +0.0000)

## by group

| group | n | score |
|---|--:|--:|
| bad_family | 1 | 0.0000 |
| cycle | 1 | 0.0000 |
| dangling_ref | 1 | 1.0000 |
| missing_name | 1 | 1.0000 |
| positive | 3 | 1.0000 |
| self_loop | 1 | 0.0000 |
| unknown_type | 1 | 1.0000 |

## worst cases (backlog)

| case | group | score | detail |
|---|---|--:|---|
| neg:cycle | cycle | 0.000 | MISS — expected ['logical'] to flag it |
| neg:bad_family | bad_family | 0.000 | validate error: {
  "error": "Validation error: Invalid operator family: 'ZZZ' (node: {'na |
| neg:self_loop | self_loop | 0.000 | MISS — expected ['logical', 'reference'] to flag it |
| good:noise_null | positive | 1.000 | clean (correct) |
| good:const_math_null | positive | 1.000 | clean (correct) |
| good:movie_level | positive | 1.000 | clean (correct) |
| neg:dangling_ref | dangling_ref | 1.000 | caught by ['reference'] (correct) |
| neg:unknown_type | unknown_type | 1.000 | caught by ['semantic'] (correct) |
| neg:missing_name | missing_name | 1.000 | caught by ['schema'] (correct) |
