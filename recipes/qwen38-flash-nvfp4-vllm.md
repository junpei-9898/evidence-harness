# Qwen3.8-Flash-Next NVFP4 — vLLM 起動レシピ（DGX Spark・実測）

重みは含めない。研究側で `qwen38-flash` プロファイルの結果（`docs/CLAIMS.md`）を測った配備は 2 種類あり、
いずれも公開レシピ（GitHub `MiaAI-Lab`）をそのまま使った。フラグはレシピの `.env` で決まる。

## A. 単一 Spark（探索面・出典ゲート契約 v2 の保存走はこちら）

- レシピ: `MiaAI-Lab/Qwen3.8-Flash-Next-Single-DGX-Spark`・checkpoint `Mia-AiLab/Qwen3.8-Flash-Next-NVFP4`（約 99 GiB）。
- 構成: TP1・PLE を host にオフロード（約 27 GiB）・`MAX_NUM_SEQS=4`（クライアント並列は 4 以下）・`KV_CACHE_DTYPE=auto`（bf16）・thinking はテンプレート既定で ON（`reasoning` が分離して返る）。
- `tools` → `tool_calls`（arguments は JSON 文字列）・`role:"tool"`・`usage`・`finish_reason` の全てが OpenAI 互換で返る。本リポの transport は無改修で接続できた。
- 起動は約 10 分（lazy load 2 パス）。ダウンロードは回線次第（40 MB/s で約 50 分）。
- **既知の落とし穴（レシピ側）**: 初回起動で `logs/archive/` が空だと `start.sh` の Step 6 直後の `ls … | tail | while` が exit 2 になり、`set -euo pipefail` により無音終了する（ログは「Step 6: Launch」で止まりコンテナは作られない）。回避は `touch logs/archive/placeholder-19700101T000000-container.log` を先に置く。
- `~/.cache/huggingface/hub` が root 所有だと `download.sh` が Permission denied になる。`HF_HOME` を書込可能な場所に向ける。

## B. 2 台 TP2（lookup 面・値形式契約の 160 問はこちら）

- レシピ: `MiaAI-Lab/Qwen3.8-Flash-Next-Dual-DGX-Sparks`・checkpoint `RadixArk/Qwen3.8-Flash-Next-NVFP4`（約 126 GB・1 台には載らない）。
- 構成: TP2＋EP・head 側の 8888 だけが API（worker は headless）・`MAX_NUM_SEQS=8`・`KV_CACHE_DTYPE=fp8`・`MAMBA_SSM_CACHE_DTYPE=bfloat16`・MTP 3（縮約語彙 draft）・`MAX_MODEL_LEN=262144`・`YARN_ENABLE=false`（native 長）・thinking 既定 ON。
- 起動は約 12 分。速度感: 探索 1 問 3〜4 ラウンドで 45〜80 s（並列 1）・lookup 8 行 44 s（並列 4）。overflow（16,384 token）は探索 120 走で 0。
- 重み検証: レシピの `check-weights.sh --verify` は HF manifest 取得で無音ハングすることがある。別マシンで manifest を取得し `--manifest FILE` で照合する。

## 配備差の開示

- lookup 面の結果（B・fp8 KV）と探索面の結果（A・bf16 KV）は配備が異なる。同じ checkpoint 名でも量子化元（Mia／RadixArk）が違う。`docs/CLAIMS.md` の各行にどちらで測ったかを併記している。
- 並列実行下では温度 0 でも再現しない（直列は決定論）。
- `docs/CLAIMS.md` の qwen3.8 の行は全て 1 draw（再現性未確認）。2 draw が要る主張には使わない。
