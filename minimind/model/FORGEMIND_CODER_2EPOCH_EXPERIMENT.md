# ForgeMind-Coder-1.5B q/v LoRA: two-epoch experiment

Optional comparison checkpoint; the one-epoch adapter remains the default because this run did not improve the fixed behavioral score.

## Run record

- Base: `Qwen/Qwen2.5-Coder-1.5B-Instruct`, pinned revision `2e1fd397ee46e1388853d2af2c993145b0f109a8`
- Data: 2,700 training rows from the 3,000-row dataset; same fixed 32-row validation sample
- Hardware: RTX 5070 Laptop, 8 GB VRAM
- LoRA: rank 8, alpha 16, q_proj/v_proj; maximum sequence length 384
- Training: 2 epochs, 5,400 microsteps, 675 optimizer updates, 976.791 seconds
- Validation loss: 0.378241 initially; best 0.337608 at step 3,900; final 0.339842
- Behavior suite: 15/17 tasks per round (45/51 generations across three repeats), matching base and one-epoch LoRA; 17/17 prompts had identical greedy output across repeats

The lower best validation loss versus the one-epoch run did not improve task correctness. This small fixed suite does not establish general coding capability or Doubao parity.

## Reproduce

```powershell
python trainer/train_forgemind_coder_lora.py `
  --data dataset/forge_magicoder_sft.jsonl `
  --data-manifest dataset/forge_magicoder_sft.jsonl.manifest.json `
  --base-model models/qwen25-coder-1.5b-instruct `
  --base-model-id Qwen/Qwen2.5-Coder-1.5B-Instruct `
  --base-revision 2e1fd397ee46e1388853d2af2c993145b0f109a8 `
  --output-dir out/ForgeMind-Coder-1.5B-LoRA-2epoch `
  --max-rows 0 --max-steps 0 --epochs 2 --max-length 384 `
  --accumulation-steps 8 --validation-rows 32 --eval-every 300 `
  --rank 8 --alpha 16 --target-modules q_proj,v_proj
```

The optional adapter archive is `output/ForgeMind-Coder-1.5B-LoRA-2epoch-实验版.zip`. Raw generations and graded task results are in the sibling `output` directory.
