# ForgeMind-Coder-0.5B LoRA

This is a local LoRA adapter for `Qwen/Qwen2.5-Coder-0.5B-Instruct`, pinned to Hub revision `ea3f2471cf1b1f0db85067f1ef93848e38e88c25`. The base model remains a separate download; this package contains only the adapter, provenance, and license notice.

## Training evidence

- Hardware: NVIDIA GeForce RTX 5070 Laptop GPU, 8 GB.
- Data: 3,000 rows from the pinned Magicoder dataset snapshot; 2,700 train rows and 300 validation rows were split deterministically. Validation used 32 fixed rows.
- Configuration: sequence length 512, LoRA rank 8 on `q_proj`/`v_proj`, gradient accumulation 8; 2,700 microsteps (one pass through the selected training rows), 338 optimizer updates, 437.128 seconds.
- Held-out token loss: 0.461781 before training; best 0.363838 at microstep 1,800. Later checks were slightly worse, so the best validation adapter was saved.
- Fixed generated-code task set: base model 4/5 and this adapter 4/5. Both fail the CSV quoted-comma task. These five tasks are a smoke benchmark, not pass@1, repository coding, or a Doubao comparison.
- Three greedy repetitions produced byte-for-byte identical output on all five prompts for both base and adapter. Functional tests over the repeated outputs passed 12/15 for each. This measures repeatability on five prompts, not general model stability; the CSV failure repeats consistently.

The small validation-loss improvement does not establish better code capability. The dataset card declares MIT, but upstream per-sample code attribution needs review; the raw derived training data is not included. The adapter's `adapter_config.json` records the dataset and base revisions, hashes, training settings, software, and loss history.

## Run locally

From the project root, download the pinned base and start the API:

```powershell
python scripts/download_forgemind_base.py --output models/forgemind-coder-0.5b-base
python scripts/serve_forgemind_coder.py `
  --adapter out/ForgeMind-Coder-0.5B-LoRA `
  --base-model models/forgemind-coder-0.5b-base `
  --host 127.0.0.1 --port 8999
```

The local HTTP endpoint has not yet passed an end-to-end request check in the managed environment. This adapter is not a MiniMind checkpoint trained from random initialization and does not demonstrate parity with Doubao.
