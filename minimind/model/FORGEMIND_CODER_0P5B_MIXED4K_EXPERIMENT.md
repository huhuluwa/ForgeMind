# ForgeMind-Coder-0.5B Mixed4k LoRA experiment

Date: 2026-10-09. Experimental adapter; not the default model.

## Training record

- Base: `Qwen/Qwen2.5-Coder-0.5B-Instruct`, revision `ea3f2471cf1b1f0db85067f1ef93848e38e88c25` (Apache-2.0).
- Data: 4,000 locally prepared rows: 2,000 filtered CodeSearchNet-derived prompts and 2,000 Magicoder rows, deduplicated by normalized user prompt. The deterministic split used 3,600 training rows and 400 validation rows; validation loss used 32 rows.
- Hardware: RTX 5070 Laptop GPU, 8 GB.
- LoRA: rank 8, alpha 16, dropout 0.05, `q_proj`/`v_proj`, max sequence length 256, learning rate `5e-5`, gradient accumulation 8, one epoch.
- Training: 3,600 microsteps, 450 optimizer updates, 0 skipped updates, 566.27 seconds.
- Validation loss: `1.22336` initially; best/final `1.02863` at step 3,600.
- Dataset SHA-256: `3a87e104a78754e5247b2709fd63ffb16ff277484bd34521581eea4aefaf6e0a`.

## Fixed behavior screen

Same 17 hand-authored function tasks, three greedy repeats, 160 generated tokens, and the same AST-limited child-process grader:

| Candidate | Passes | Per repeat | Exact repeatability |
| --- | ---: | ---: | ---: |
| 0.5B base | 30/51 | 10/17 | 17/17 prompts |
| 0.5B + Mixed4k LoRA | 39/51 | 13/17 | 17/17 prompts |

The adapter adds `flatten_once`, `merge_sorted`, `normalize_spaces`, and `transpose`; it regresses `dedupe_order`. It still fails `average_positive`, `dedupe_order`, quoted CSV parsing, and `rotate_left`. This is a narrow improvement on a small function suite, not repository-level coding or Doubao parity. The 1.5B base remains stronger on this screen at 15/17; this adapter is not a replacement for that baseline.

Raw generations and per-case grades are in `eval/results/forgemind_coder_0p5b_mixed4k_repeat3.jsonl` and `eval/results/forgemind_coder_0p5b_mixed4k_function_repeat3.jsonl`. The adapter config records the pinned model, dataset hashes, optimizer settings, losses, and runtime versions. The large base model is separate.

## Reproduce

```powershell
python trainer/train_forgemind_coder_lora.py `
  --data dataset/forge_coder_mixed_4k.jsonl `
  --data-manifest dataset/forge_coder_mixed_4k.jsonl.manifest.json `
  --base-model models/qwen25-coder-0.5b-instruct `
  --base-model-id Qwen/Qwen2.5-Coder-0.5B-Instruct `
  --base-revision ea3f2471cf1b1f0db85067f1ef93848e38e88c25 `
  --model-name ForgeMind-Coder-0.5B-Mixed4k-1epoch `
  --output-dir output/weights/ForgeMind-Coder-0.5B-Mixed4k-1epoch `
  --max-rows 0 --max-steps 0 --epochs 1 --max-length 256 `
  --accumulation-steps 8 --validation-rows 32 --eval-every 300 `
  --rank 8 --alpha 16 --learning-rate 0.00005 --target-modules q_proj,v_proj
```

The CodeSearchNet-derived source records that underlying project licenses vary. The prepared mixture and adapter remain experimental; review source attribution and licenses before redistribution or commercial use.

## Two-epoch comparison

The same base revision, dataset hash, split seed, LoRA target modules, length, learning rate, and validation sample were used for a separate two-epoch run. It completed 7,200 microsteps / 900 optimizer updates in 1,119.88 seconds. One non-finite optimizer update at step 4,912 was skipped by GradScaler; training recovered. Best validation loss was 1.01761 at step 6,600, slightly below the one-epoch best of 1.02863.

The two-epoch adapter passed 36/51 generations (12/17 per repeat), below one epoch's 39/51 (13/17). Both adapters were exactly repeatable on all 17 prompts. The two-epoch run regressed `normalize_spaces` compared with one epoch while retaining its `dedupe_order` regression. Keep the one-epoch adapter as the stronger 0.5B candidate for this fixed screen; do not choose an adapter from validation loss alone. Two-epoch outputs are in `eval/results/forgemind_coder_0p5b_mixed4k_2epoch_repeat3.jsonl` and `eval/results/forgemind_coder_0p5b_mixed4k_2epoch_function_repeat3.jsonl`.

## Lower-learning-rate comparison

A matched one-epoch run changed only the learning rate from `5e-5` to `2e-5`; the base revision, data and split, q/v targets, rank 8, sequence length, batch accumulation, validation sample, decoding, and grader were unchanged. It completed 3,600 microsteps / 450 optimizer updates in 567.10 seconds. Validation loss moved from 1.22336 to 1.04400. One non-finite gradient update at step 2,088 was skipped by GradScaler, which lowered its scale and continued training.

The low-learning-rate adapter also passed 39/51 generations (13/17 tasks per repeat), and all 17 prompts were exactly repeatable. Its per-task pass set matched the `5e-5` one-epoch candidate; it did not fix an additional task. Since its best behavior is tied and its validation loss is slightly higher, keep `5e-5` as the default one-epoch candidate. Results: `eval/results/forgemind_coder_0p5b_mixed4k_lr2e5_repeat3.jsonl` and `eval/results/forgemind_coder_0p5b_mixed4k_lr2e5_function_repeat3.jsonl`.

## Rank-16 comparison

A matched one-epoch experiment raised only LoRA rank from 8 to 16 and alpha from 16 to 32, keeping the scaling ratio at 2; all other settings were held fixed at the `5e-5` learning rate. It completed 3,600 microsteps / 450 optimizer updates in 568.47 seconds, with no skipped updates. Best/final validation loss was 1.0208.

The rank-16 adapter passed 36/51 generations (12/17 per repeat), below the rank-8 one-epoch adapter's 39/51. All 17 prompts were exactly repeatable. This higher-capacity adapter is not the preferred candidate for the fixed screen, despite its lower validation loss. Results: `eval/results/forgemind_coder_0p5b_mixed4k_r16_repeat3.jsonl` and `eval/results/forgemind_coder_0p5b_mixed4k_r16_function_repeat3.jsonl`.

