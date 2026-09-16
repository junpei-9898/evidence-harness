# DIFFERENTIAL.md — 差分試験の契約

移植版が研究側と**同じ要求を同じ順序で送り、同じ判定を下す**ことを保証する。保存応答のリプレイ
だけでは不足（応答が同じでも次の要求が違えば別実装）なので、要求列と判定列を照合する。

## 1. 照合対象

- **要求列**: transport に渡された payload ごとに、`task_id` を除去し `json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))` の sha256 を取った列。ヘッダは対象外。
- **判定列**: プロファイルごとに定義する順序つき決定の列。
  - explore-v4: 各ラウンドの `executions[*].result` の sha256（tool 実行結果）・`stall_judgments[*].fired/reasons`・最終 `gate.reason`（`passed|abstain|missing_source|missing_quote|source_not_fetched|quote_not_verbatim`）・`gate.quote_length_ok`。
  - lookup-pc: `landing_source`（`native|b3|finalizer|None`）・`b3_reason`・`harness_rejected`・`reject_reason`・`extra_calls`・`model_calls`・出荷 `answer/nonce`。
  - lookup-c: 上記＋`gate_fired`・`checkpoint`・`strict_reject_reason`・retrieval の合成呼び出し引数列。
  - rules: `complete()` の返す dict 全体。
- fixture の `expected` は、研究側の凍結モジュールを研究側チェックアウトの上で実行する参照実装ドライバ（研究側に置く・本リポには含めない）で生成し、fixture に焼き込む。本リポの CI は焼き込まれた値との一致だけを検査する。移植版の出力を expected に写すことは禁止。

## 2. fixture 形式（`tests/differential/fixtures/<profile>/<id>.json`）

```json
{
  "id": "explore-gate-quote-mismatch-01",
  "profile": "explore-v4",
  "branch_tags": ["gate:quote_not_verbatim", "paging:has_more"],
  "workdir": {"files": {"docs/a.md": "...synthetic..."}},
  "question": "...synthetic...",
  "config": {"max_rounds": 6, "max_tokens": 16384, "temperature": 0},
  "responses": [ {"choices": [{"message": {...}, "finish_reason": "tool_calls"}], "usage": {...}} ],
  "expected": {
    "request_sha256": ["..."],
    "decisions": {...}
  }
}
```

- `responses` はスクリプト化された transport 応答（順番に返す）。応答の数が足りない要求が出た時点で fixture は FAIL（＝要求列の長さも検査される）。
- `workdir.files` は試験時に一時ディレクトリへ展開する。本文・パス・質問は**合成**（研究側 transcript からの機械抽出は「分岐の形」だけを写し、内容は生成器で置換する）。
- `branch_tags` は §3 の被覆表と機械照合する（`tests/differential/test_coverage.py`）。

## 3. 分岐被覆（床 48 件・全タグ 1 件以上）

| 群 | タグ |
|---|---|
| v4 paging | `paging:offset` `paging:line` `paging:both_given` `paging:max_chars_boundary` `paging:beyond_end` `paging:line_out_of_range` `paging:has_more` |
| v4 grep | `grep:rows` `grep:regex_fallback` `grep:time_capped` `grep:scope_file` `grep:scope_missing` |
| glob | `glob:dir_marker` `glob:excluded_dir` `glob:truncated` |
| tools 異常 | `tool:bad_json` `tool:unknown_name` `tool:extra_keys` `tool:root_escape_dotdot` `tool:root_escape_abs` `tool:root_escape_symlink` |
| 出典ゲート | `gate:passed` `gate:abstain` `gate:missing_source` `gate:missing_quote` `gate:source_not_fetched` `gate:quote_not_verbatim` `gate:quote_length_short` `gate:quote_multiline_escape` |
| stall 観測 | `stall:duplicate_request` `stall:no_new_path_or_span` `stall:single_document_type` `stall:not_fired` `stall:continuation_read` |
| 予算 | `budget:round_cap` `budget:length_overflow` |
| lookup native | `pc:native_grounded` `pc:native_ungrounded` |
| B3 | `b3:not_cap` `b3:no_draft` `b3:conflicting_drafts` `b3:compound_answer` `b3:nonce_ungrounded` `b3:landed` `b3:duplicate_key_json` |
| 救済 finalize | `fin:accepted` `fin:unparseable` `fin:empty_nonce` `fin:nonce_ungrounded` `fin:reads_only_payloads` |
| C 層 | `c:early_gate_fired` `c:retrieve_0` `c:retrieve_1` `c:retrieve_2` `c:already_read_excluded` `c:strict_nonce_not_exact_token` `c:strict_answer_is_nonce_shaped` `c:reset_finalize_accept` `c:rescue_after_natural_nonland` |
| 規則 | `ra:bare_digits` `ra:unique_digit_token` `ra:ambiguous` `ra:no_digit` `rb:all_identifiers` `rb:non_identifier` `rb:empty` |
| transport | `tx:error_then_retry_ok` `tx:error_twice` `tx:bad_response_shape` |

## 4. 合格条件

- 全 fixture で要求列 sha256 が完全一致（長さ含む）・判定列が完全一致。
- 被覆表の全タグに 1 件以上・総数 ≥48。
- 実 FS の root 逸脱試験（`tests/test_root_escape.py`）が `..`・絶対パス・symlink の 3 経路で fail-closed。
- 研究側の凍結モジュール digest（`docs/PORTING.md` §1）と移植元ファイル一式の digest が研究側の照合スクリプトで一致（研究側チェックアウトがある環境のみ・本リポの CI では行わない）。
