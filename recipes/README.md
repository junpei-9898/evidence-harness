# recipes

公開重みを OpenAI 互換で起動するための実測フラグ。重みは含めない。

- `qwen36-base-nvfp4-vllm.md`（Qwen3.6-35B-A3B NVFP4・MTP あり・gpu util 0.80）
- `qwen36-mercor-nvfp4-vllm.md`（Mercor NVFP4・**no-MTP**・gpu util 0.70・並列 ≤6・hang/crash 開示）
- `qwen38-flash-nvfp4-vllm.md`（Qwen3.8-Flash-Next NVFP4・単一 Spark／2 台 TP2 の配備 2 種・**全数値 1 draw**）
