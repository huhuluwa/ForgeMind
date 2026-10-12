# ForgeMind-Coder 1.5B mixed-data LoRA comparison

Date: 2026-10-09  
Base: `Qwen/Qwen2.5-Coder-1.5B-Instruct`, revision `2e1fd397ee46e1388853d2af2c993145b0f1098a`  
Hardware: NVIDIA RTX 5070 Laptop, 8 GB VRAM

## Matched training runs

Both runs use the same 4,000-row dataset (`dataset/forge_coder_mixed_4k.jsonl`, 3,600 training and 400 validation rows), split seed `20261010`, 64-row validation loss sample, q/v LoRA rank 8 / alpha 16, dropout 0.05, length 384, accumulation 8, and 450 optimizer updates. Learning rate is the only changed training variable.

| Learning rate | Initial loss | Best/final validation loss | Time | Skipped updates |
| --- | ---: | ---: | ---: | ---: |
| `5e-5` | 0.80362 | 0.67189 | 684.24 s | 0 |
| `2e-5` | 0.80362 | 0.68238 | 954.74 s | 0 |

## Behavior evaluation

Both adapters were reevaluated with the same 17 tasks, three greedy repeats, maximum 160 generated tokens, and AST-limited child-process grader. Each passed 45/51 generations (15/17 tasks per repeat), matching the base model. Both adapters fail `flatten_once` and quoted-CSV parsing. All 17 prompts produced exactly repeatable output across the three repetitions. The lower learning rate did not improve behavior and had slightly higher validation loss, so retain `5e-5` as the default mixed-data 1.5B candidate for this fixed screen.

Raw and graded outputs:

- `5e-5`: `eval/results/forgemind_coder_1p5b_mixed4k_lr5e5_repeat3_matched.jsonl`, `eval/results/forgemind_coder_1p5b_mixed4k_lr5e5_function_repeat3_matched.jsonl`
- `2e-5`: `eval/results/forgemind_coder_1p5b_mixed4k_lr2e5_seed20261010_repeat3.jsonl`, `eval/results/forgemind_coder_1p5b_mixed4k_lr2e5_seed20261010_function_repeat3.jsonl`

The first `2e-5` trial used seed 42; it is archived with `seed42_exploratory` filenames and excluded from the paired claim. These results are limited to a small function screen. They do not establish repository-level quality or Doubao parity. Review the underlying data licenses before redistributing trained weights.
