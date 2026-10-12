# ForgeMind data preparation notes

## Small free coding SFT pilot

`trainer/prepare_magicoder_sft.py` streams a bounded, shuffled subset from the official [Magicoder OSS-Instruct 75K card](https://huggingface.co/datasets/ise-uiuc/Magicoder-OSS-Instruct-75K), pins the resolved Hub commit, filters empty/oversize records, deduplicates prompt-answer pairs, and writes the `conversations` shape consumed by `SFTDataset`. Its default is 3,000 rows to keep the first run small. The script also writes a JSON manifest containing the source revision and output SHA-256.

```powershell
python trainer/prepare_magicoder_sft.py --output dataset/forge_magicoder_sft.jsonl --max-rows 3000 --seed 42
```

The dataset card declares MIT. The upstream project describes the data as generated from permissively licensed open-source code snippets, but each derived sample does not carry a complete source-repository attribution field. Retain the dataset notice and review relevant upstream terms before redistributing the prepared data or using it commercially. The instruction text is primarily English; it is not evidence of Chinese coding ability. Pass `--revision <40-character commit SHA>` from the manifest to reproduce against the same source snapshot.

## Chinese corpus caution

COIG-PC-core is a large Chinese instruction collection whose card assigns Apache-2.0 by default only to subsets without a more specific license; explicitly declared subset terms take precedence. Because the corpus aggregates many upstream sources and the row-level source-license mapping has not been audited here, this repository does not automatically download or ingest it. Keep a source allowlist and exclude subsets without verifiable provenance.

## Training limits

The pilot is for checking the SFT pipeline or adapting a compatible pretrained checkpoint. A few thousand instruction examples cannot substitute for the large, diverse next-token corpus needed to pretrain a 1B or 7B model from scratch. Do not claim target-model capability from a smoke run or training loss alone. Evaluate code with fixed tasks and sandboxed tests.
