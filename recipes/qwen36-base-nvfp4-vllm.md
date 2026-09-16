# Qwen3.6-35B-A3B NVFP4（base）— vLLM 起動レシピ（実測・DGX Spark GB10 1 基）

重みは含めない。`unsloth/Qwen3.6-35B-A3B-NVFP4` revision `739af1e7aac320af1682ed1e0cce369af4c5265d` を
Hugging Face から取得し、下記フラグで起動した構成が研究側の base 測定条件（`docs/CLAIMS.md` の base 行）である。

- イメージ: `ghcr.io/miaai-lab/mia-vllm-gb10-linear-b12x:latest`（`--network host`・`--gpus all`・`--ipc host`・`--shm-size=32g`・`-e CUTE_DSL_ARCH=sm_121a`）
- `vllm serve <model> --revision <rev> --served-model-name qwen36 --tensor-parallel-size 1 --trust-remote-code --moe-backend auto --gpu-memory-utilization 0.80 --linear-backend flashinfer_b12x --attention-backend flashinfer --max-model-len 262144 --max-num-seqs 24 --max-num-batched-tokens 32768 --enable-chunked-prefill --async-scheduling --kv-cache-dtype fp8 --speculative-config '{"method":"mtp","num_speculative_tokens":2,"moe_backend":"triton"}' --reasoning-parser qwen3 --default-chat-template-kwargs '{"enable_thinking":true,"preserve_thinking":true}' --tool-call-parser qwen3_coder --enable-auto-tool-choice --override-generation-config '{"temperature":0.6,"top_p":0.95,"top_k":20,"min_p":0.0,"presence_penalty":0.0,"repetition_penalty":1.0}'`
- 研究側の測定は上記に LoRA モジュールを併載した構成（本リポには無関係・base 名で呼べば base に当たる）。
- クライアント側の予算: explore-v4 は `max_tokens 16384`・`temperature 0`・HTTP timeout 900 s。lookup-pc は `max_tokens 4096`・`temperature 0.7`（実効 top_p 0.95／top_k 20 はサーバ上書き）。
- 並列: 研究側実測で 8〜12 並列が実用帯（1 本 28〜32 tok/s）。**NVFP4 は温度 0 でも並列下で非決定論**（同一入力の draw 間で結果が割れる）。再現比較は同一機・直列で取る。

## 開示
- 研究側の測定は 2 台の同一構成ノードで行い、rep ペアは同一機で取った。
- `tool_choice` は全種が動作。`usage` は返る。`message.reasoning` に思考が分離される。
