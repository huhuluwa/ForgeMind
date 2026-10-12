# ForgeMind-Coder 1.5B: known-overlap row exclusion ablation

Date: 2026-10-09  
Base: Qwen2.5-Coder-1.5B-Instruct, revision `2e1fd397ee46e1388853d2af2c993145b0f1098a`  
GPU: NVIDIA RTX 5070 Laptop, 8 GB VRAM

## Training

This matched-seed run uses the mixed4k dataset after removing the four SFT rows confirmed by the benchmark overlap audit (1,052, 1,965, 2,822, 3,470). It retains the q/v LoRA rank 8 / alpha 16 / dropout 0.05, max length 384, learning rate `5e-5`, accumulation 8, and seed `20261010` settings. Dataset lineage and SHA-256 are in `dataset/forge_coder_mixed_4k_overlap4_excluded.jsonl.manifest.json`.

| Measure | Result |
| --- | ---: |
| Dataset rows | 3,996 |
| Training microsteps | 3,597 |
| Optimizer updates | 450 |
| Time | 932.91 s |
| Skipped updates | 0 |
| Initial validation loss | 0.79855 |
| Best/final validation loss | 0.67999 at step 3,597 |

## Behavior

Using 17 fixed tasks, three greedy repeats, 160 generated tokens, and the same AST-limited child grader:

| Candidate | Passed | Failed tasks | Repeatable prompts |
| --- | ---: | --- | ---: |
| 1.5B base | 15/17 | `flatten_once`, `parse_csv_line` | 17/17 |
| New overlap-row-exclusion LoRA | 15/17 | `flatten_once`, `parse_csv_line` | 17/17 |

Removing the four known SFT rows did not change the score or failure set. The result ties the base and does not demonstrate a behavior gain. The training corpus is not fully decontaminated, and the base model's pretraining data cannot be inspected; the fixed screen remains diagnostic only.

Raw generations: `eval/results/forgemind_coder_1p5b_mixed4k_overlap4excluded_repeat3.jsonl`  
Graded outputs: `eval/results/forgemind_coder_1p5b_mixed4k_overlap4excluded_function_repeat3.jsonl`  
Adapter: `output/weights/ForgeMind-Coder-1.5B-Overlap4Excluded-LR5e5/`

Reproduction command (run from `minimind-product`):

```powershell
python trainer/train_forgemind_coder_lora.py `
  --data dataset/forge_coder_mixed_4k_overlap4_excluded.jsonl `
  --data-manifest dataset/forge_coder_mixed_4k_overlap4_excluded.jsonl.manifest.json `
  --base-model ../tmp/models/qwen25-coder-1.5b-instruct `
  --base-model-id Qwen/Qwen2.5-Coder-1.5B-Instruct `
  --base-revision 2e1fd397ee46e1388853d2af2c993145b0f1098a `
  --model-name ForgeMind-Coder-1.5B-Overlap4Excluded-LR5e5 `
  --output-dir output/weights/ForgeMind-Coder-1.5B-Overlap4Excluded-LR5e5 `
  --max-rows 0 --max-steps 0 --epochs 1 --max-length 384 `
  --accumulation-steps 8 --validation-rows 64 --eval-every 300 `
  --rank 8 --alpha 16 --learning-rate 0.00005 `
  --target-modules q_proj,v_proj --seed 20261010
```

This experiment only removes four known overlaps. It is not the final held-out code-development benchmark and was not compared with Doubao because no Ark credentials are configured.

## Repository-level coding pilot (2026-10-09)

A separate four-task, multi-file pilot tested direct full-file code generation and the tool Agent. Direct generation used the same 2,048-token greedy decoding budget for base and adapter. Base passed 4/26 fixed cases; the overlap-excluded adapter passed 2/26. Neither completed all hidden cases for any of the four tasks. The tool Agent also completed 0/4 and repeatedly failed to use valid tool names or move past duplicate reads. Full protocol, limitations, scripts, and raw JSON are in [`../eval/FORGEMIND_REPO_AGENT_PILOT_V1.md`](../eval/FORGEMIND_REPO_AGENT_PILOT_V1.md).

This pilot is a warning that the earlier 15/17 short-function score does not transfer to multi-file repository work. The adapter did not improve over its base. Four hand-written tasks do not constitute a broad SWE benchmark, and there is no same-condition Doubao comparison because no Ark credentials are present.
