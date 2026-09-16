# SPEC_explore.md — 探索プロファイル `explore-v4`

用途: 作業ディレクトリ（読み取り専用）を tools で探索し、**出典と逐語引用つき**で答える。
引用が取得済み証拠と一致しない回答は出荷せず、定型の不能文に置換する。

## 1. ループ（研究側 `run_task_v3` と同一・reset なし）

1. `messages = [system, user]`。system は `SYSTEM_EXPLORE + "\n" + ANSWER_FORMAT`（両文字列は byte 同一に移植）。
2. 最大 `max_rounds=6` 回、`{"model", "messages", "tools": TOOLS_V4, "temperature": 0, "max_tokens"}` を送る。
3. 応答 `message.tool_calls` が空なら終了。あれば assistant メッセージを追加し、各 call を v4 tools で実行し `role:"tool"` に `json.dumps(result, ensure_ascii=False)` を載せる。
4. ラウンド 2 と 3 の後に `stall_check` を評価し記録する（**介入しない**）。
5. 最終 `message.content` に `apply_gate(content, Ledger(rounds, manifest))` を適用。`gated_content` を出荷する。

## 2. tools v4

- `read_file(path, offset|line, max_chars≤8000)`: `offset` と `line` は排他（両方で `wellformed=false`）。返り値 `start/end/start_line/total_chars/has_more/next_offset`。`line` 超過は `line_out_of_range`。
- `grep(pattern, path="")`: 行 `path:line:char_offset:text`＋構造化 `rows`。10 秒予算超過は `[TIME_CAPPED]` 先頭行。regex 不正は部分文字列一致に fallback。
- `glob(pattern)`: 除外表（`node_modules` 等）に従う。`dir_marker=False`（研究側 V4 と同じ）。
- 全 tool: `..`・絶対パス・root 外 symlink は fail-closed（`wellformed=false` または空結果）。

## 3. 出典ゲート

- 回答末尾の `出典: <path>` / `引用: <20〜200 字>` の 2 行を読む（本文からの推測はしない）。
- `出典` が Ledger の取得済みパスに無い → `source_not_fetched`。引用が取得済み read 片・grep 行に空白正規化で含まれない → `quote_not_verbatim`。いずれも `GATE_FAILURE` 文に置換。
- 本文に `ABSTAIN_TEXT` を含み出典行が無い → 棄権として通す。

## 4. 監視計器（`instruments/`）

引用ゲート通過率・棄権率・`finish_reason=length`（overflow）率・round cap 到達率・usage 合計・成功当たりトークン・stall 発火（観測）。

## 5. 既定と適用範囲の記述

qwen3.6-35B-A3B NVFP4（vLLM・thinking ON）・実リポ lookup 質問・round 6・max_tokens 16,384 で研究側が判断採用した構成。Mercor checkpoint は候補併記（`docs/CLAIMS.md`）。
