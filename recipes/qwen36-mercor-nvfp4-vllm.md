# Qwen3.6-35B-A3B Mercor NVFP4 — vLLM 起動レシピ（実測・**no-MTP**）

重みは含めない。`mercor/Qwen3.6-35B-A3B-Mercor`（rev `1585b21d`）を modelopt NVFP4（W4A16・lm_head BF16）に
量子化したローカル checkpoint を、研究側で下記フラグで起動した（`docs/CLAIMS.md` の Mercor 行）。量子化手順は本リポの範囲外。

- イメージ・docker フラグは base と同一。
- `vllm serve /path/to/qwen36-mercor-nvfp4 --served-model-name qwen36-mercor --tensor-parallel-size 1 --trust-remote-code --moe-backend auto --gpu-memory-utilization 0.70 --linear-backend flashinfer_b12x --attention-backend flashinfer --max-model-len 262144 --max-num-seqs 24 --max-num-batched-tokens 32768 --enable-chunked-prefill --async-scheduling --kv-cache-dtype fp8 --reasoning-parser qwen3 --default-chat-template-kwargs '{"enable_thinking":true,"preserve_thinking":true}' --tool-call-parser qwen3_coder --enable-auto-tool-choice --override-generation-config '{"temperature":0.6,"top_p":0.95,"top_k":20,"min_p":0.0,"presence_penalty":0.0,"repetition_penalty":1.0}'`
- **`--speculative-config` を付けない（no-MTP）**・`--gpu-memory-utilization 0.70`・クライアント並列は **6 以下**。
- 探索面（explore-v4・16k 予算）の overflow 走は最大 3,600 s かかる＝HTTP timeout は 3,600 s。

## 開示（hang／crash）
- base と同一フラグ（MTP 2・gpu util 0.80・並列 10）では 1〜1.5 時間ごとにエンジンが 0 tok/s で固まり、続いて `cudaErrorIllegalAddress` でコンテナが終了した（2 台で計 5 回）。MTP は受理 0 token で実効なしだった。
- 対処は全て配備／transport 側（上記 3 点＋逐次永続化と再開）。サンプリング・予算・採点は不変。
- 停止検知は throughput 0 だけでは不十分（落ちたコンテナのログは最終行が固定される）。コンテナ生存と throughput 行の stale を併せて見る。
- 上記は当該 checkpoint・当該イメージでの観測であり、原因の特定はしていない。
