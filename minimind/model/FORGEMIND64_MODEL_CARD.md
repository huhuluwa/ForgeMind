# ForgeMind-64M

ForgeMind-64M is a small model initialized from random weights and trained locally through a MiniMind-derived pipeline. It shares the project's 6,400-token MiniMind tokenizer and decoder implementation; both checkpoints below start without MiniMind or Qwen pretrained weights.

## Architecture

- Profile: `forgemind64`
- Decoder layers: 8; hidden size: 768; attention heads: 8 query / 4 KV
- FFN size: 2,432; vocabulary: 6,400; context: 4,096
- Approximate parameter count: 64.0M

## Training and limits

Two free-resource runs used a locally prepared 3,000-row Magicoder-derived sample on an RTX 5070 Laptop (8 GB), with 256-token sequences, batch size 2, gradient accumulation 8 and bfloat16. The direct-SFT run used five epochs (7,500 microsteps / 940 optimizer updates), ending at training loss 2.54. The second run pretrained for five epochs on assistant response text, then performed five SFT epochs; training loss ended at 1.24 and 0.66 respectively. Neither run used a held-out validation split, so these are training-loss measurements only.

Both checkpoints loaded and generated locally, but each failed all 51 generations of the fixed 17-task Python behavior screen (0/17 tasks per round). Outputs were identical across three greedy repeats for all 17 prompts, which means the incorrect answers were repeatable. These are not usable coding models, have not been compared with Doubao, and are far below the separate 1.5B Qwen-derived ForgeMind-Coder candidate.

The tokenizer is inherited from the MiniMind project. The dataset manifest carries the source revision and license caveat; review upstream code attribution before redistribution or commercial use.

## Train from scratch

From `minimind-product/trainer`, with the prepared 3,000-row dataset at `../dataset/forge_magicoder_sft.jsonl`:

```powershell
python train_full_sft.py `
  --profile forgemind64 --tokenizer_path ../model `
  --data_path ../dataset/forge_magicoder_sft.jsonl `
  --from_weight none --save_weight forgemind64_sft `
  --save_dir ../output/weights/ForgeMind-64M-from-scratch `
  --epochs 1 --batch_size 2 --accumulation_steps 8 `
  --max_seq_len 256 --learning_rate 0.0002 --dtype bfloat16
```

The checkpoints are standalone model weights; they do not need a Qwen base. The matching tokenizer is the project's `model/` directory.

## Run locally

From the same `trainer/` directory:

```powershell
python ../scripts/serve_openai_api.py `
  --load_from ../model --profile forgemind64 --tokenizer_path ../model `
  --save_dir output/weights/ForgeMind-64M-from-scratch `
  --weight forgemind64_sft --device cuda --host 127.0.0.1
```

The server listens on port 8998 by default. This is a local API endpoint. A successful model load and generated response prove the inference path works; they do not prove response quality.
