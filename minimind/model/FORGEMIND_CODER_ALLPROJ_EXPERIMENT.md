# ForgeMind-Coder-1.5B All-Projection Experiment

This is a controlled LoRA experiment, not the recommended deployment adapter. It starts from `Qwen/Qwen2.5-Coder-1.5B-Instruct` at revision `2e1fd397ee46e1388853d2af2c993145b0f109a8` and uses the same 3,000-row Magicoder-derived dataset as the q/v adapter.

## Training

- GPU: RTX 5070 Laptop, 8 GB VRAM
- Training/validation: 2,700/300 rows, with the same fixed 32-row validation sample
- LoRA: rank 8, alpha 16, dropout 0.05
- Target suffixes: `q_proj,k_proj,v_proj,o_proj,gate_proj,up_proj,down_proj`
- Max sequence length: 256; accumulation: 8
- Training: 2,700 microsteps, 338 optimizer updates, 819.205 seconds
- Best validation loss: 0.392704 at step 2,100; initial loss 0.427733
- Trainable parameters: 9,232,384; peak observed GPU use: about 6.96 GB

## Held-out behavior

On the same 17 fixed function tasks, greedy decoding, max 160 tokens, and three repeats, it passed 45/51 generations (15/17 tasks per round). The base and q/v adapter scored the same. All 17 prompts returned identical text across repeats. All three candidates consistently failed quoted CSV parsing and the one-level-only flattener task.

The all-projection adapter used 9,232,384 trainable parameters, about 8.5 times the 1,089,536 trainable parameters in 1.5B q/v LoRA. Its validation loss was worse (0.392704 vs 0.33848), and it did not improve this behavior score. Keep it for reproducible comparison; do not select it as the default.

## Reproduce

```powershell
python trainer/train_forgemind_coder_lora.py `
  --data dataset/forge_magicoder_sft.jsonl `
  --data-manifest dataset/forge_magicoder_sft.jsonl.manifest.json `
  --base-model models/qwen25-coder-1.5b-instruct `
  --base-model-id Qwen/Qwen2.5-Coder-1.5B-Instruct `
  --base-revision 2e1fd397ee46e1388853d2af2c993145b0f109a8 `
  --output-dir out/ForgeMind-Coder-1.5B-LoRA-AllProj `
  --max-rows 0 --max-steps 0 --max-length 256 `
  --accumulation-steps 8 --validation-rows 32 --eval-every 300 `
  --rank 8 --alpha 16 `
  --target-modules q_proj,k_proj,v_proj,o_proj,gate_proj,up_proj,down_proj
```

See [`../eval/FORGEMIND_EXPANDED_EVAL.md`](../eval/FORGEMIND_EXPANDED_EVAL.md) for scope and raw result paths.
