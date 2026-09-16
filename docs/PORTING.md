# PORTING.md — 移植の記録

本リポのコードは、作者の非公開研究リポジトリ（以下「研究側」）で凍結計器として使っていた
ハーネス部品を**最小抽出＋アダプタ**で移植したものである。研究側の部品は不変で、本リポは
「移植（port）」であって「移設」ではない。研究側で測定された結果は本リポの実績ではない
（`docs/CLAIMS.md` 参照）。

移植元ファイルごとの digest と関数レベルの対応表は、研究側の非公開ディレクトリに完全台帳として
置き、研究側チェックアウト上で照合する。本リポには公開に必要な要約だけを載せる。

## 1. 凍結している規則の digest

以下は本リポに含まれる規則モジュールの byte 凍結値（研究側と同一）。

- 決定論的補完（R-A/R-B）: `e65a65a44c1120b50cb2e1f1e23b69396a80635a517d11e511b945cd72e163d3`
- 同一性ゲート strict（identity-strict-1.0）: `6ae27022f36a9d8b40cddacf0c2ce08f084b8e43164e3f9d6b6afcba3ad9e7ff`
- 識別子抽出（region-repair-1.0）: `a099e3f0de2dd5b6341c4a8ff26124c24e10286cfe58eb682f76aec25a26de40`
- 下書き拾い: `B3_VERSION = "1.2"`

## 2. 部品対応表

| 系統 | 本リポ | 既定 | 備考 |
|---|---|---|---|
| tools（base 契約） | `evidence_harness/tools/base.py` | lookup-pc で ON | `read_file` の suffix/basename 解決（`resolution` フィールド）は挙動同一。修復分岐は移植せず `"off"` 固定 |
| tools（除外表） | `evidence_harness/tools/exclusions.py`, `tools/v4.py` | explore-v4 で ON | 除外表は作業ディレクトリから毎回構築する（研究側は凍結 snapshot ごとに保存していた） |
| tools（v4 座標橋） | `evidence_harness/tools/v4.py` | explore-v4 で ON | grep 行 `path:line:char_offset:text`・`read_file(path, offset\|line, max_chars≤8000)` 排他 |
| tools schema | `evidence_harness/tools/schema.py::{TOOLS_BASE,TOOLS_V4}` | — | 説明文は研究側と byte 同一（要求列 hash に含まれる） |
| transport | `evidence_harness/transport.py` | ON | urllib → httpx に置換。研究側が測定記録制御のために送っていた独自ヘッダと `task_id` は送らない（要求列 hash の対象は payload のみ） |
| メッセージ組立 | `evidence_harness/loop/messages.py` | ON | tool result は `json.dumps(result, ensure_ascii=False)` で `role:"tool"` に載せる（byte 同一） |
| 探索ループ | `evidence_harness/profiles/explore.py::run_explore` | ON | reset なし・手順プロンプトなし・`max_rounds=6`。system は探索 system＋改行＋回答形式文。state 描画・証拠パック finalize は移植しない |
| 出典ゲート | `evidence_harness/gates/citation.py` | ON | 空白正規化・`出典:`/`引用:` 2 行契約は byte 同一 |
| Ledger | `evidence_harness/loop/ledger.py` | ON | `manifest` は空 `{"files": {}}` を許容（doctype は全て `その他`） |
| stall 観測 | `evidence_harness/instruments/stall.py` | 観測のみ | 発火しても介入しない（記録のみ） |
| lookup ループ | `evidence_harness/profiles/lookup.py::run_lookup` | ON | 凍結 snapshot 封じ込めを外し作業ディレクトリ root 直結。`state` は `{system, question, tools}` の最小形 |
| 下書き拾い（B3） | `evidence_harness/gates/draft.py` | ON | 着地判定は構造条件のみ（研究側の fallback 経路と同一）。gold 比較は移植しない |
| 救済 finalize | `evidence_harness/gates/finalize.py` | ON | 履歴なし・tools なし・`max_tokens`・thinking 有効化 kwargs。保持型 finalizer は移植しない |
| grounding | `evidence_harness/gates/grounding.py` | ON | byte 同一 |
| C 層 | `evidence_harness/profiles/lookup_c.py`, `gates/identity.py` | **OFF** | Pc の上に重ねる。retrieval は grep `nonce` → 未読候補 ≤2 read の合成呼び出し |
| 規則 R-A/R-B | `evidence_harness/rules/deterministic.py` | **OFF** | byte 凍結（digest は §1）。数値 lookup 契約のタスクにのみ明示 ON |
| 計器 | `evidence_harness/instruments/usage.py`, `instruments/monitors.py` | ON | 要求/応答を改変しない |
| system prompt（lookup／explore） | 各 profile モジュールの `SYSTEM` | ON | byte 同一 |
| 公開 lookup 合成生成器 | `battery/lookup_families.py` | 診断 CLI で明示実行 | 指定 6 型の純粋生成部分だけを抽出し公開 item 形式へ変換。gold は作業ディレクトリへ展開しない |

## 3. 移植しなかったもの（評価専用依存）

| 研究側の機能 | 本リポでの扱い |
|---|---|
| 凍結 snapshot の封じ込め sandbox | 作業ディレクトリ root 直結。root 逸脱は tools 側で fail-closed（実 FS 試験 `tests/test_root_escape.py`） |
| 測定用 retry ラッパ | `instruments/usage.py::retrying` に統一 |
| 測定 state・gold 参照・正答比較・失敗段分類 | 移植しない。gold は持ち込まない |
| 着地採点の集計・レポート生成 | 移植しない（構造条件のみ使用） |
| 測定行・checkpoint 続行・アーム走行 | 移植しない（`Result` dataclass に置換） |
| reset／証拠パック finalize | 移植しない（研究側で不採用） |
| doctype manifest 構築 CLI と規則表 | 移植しない |
| 旧ループ・プロンプト変種・r1/r2 修復 | 移植しない |
| 測定記録制御の独自ヘッダ／payload `task_id` | 送らない（差分試験の hash は payload から `task_id` を除いた形で両側を照合） |

## 4. 互換 API の契約（作者環境で確認・未確認は「未確認」のまま）

| 項目 | vLLM（実測） | mlx_lm.server | Ollama |
|---|---|---|---|
| `tools` → `message.tool_calls` 往復・`role:"tool"` | ✓ | ✓（実測） | ✓ |
| `message.reasoning`／`reasoning_content` | `reasoning`（`--reasoning-parser qwen3`） | `reasoning` | 未確認（無い場合、下書き拾いは `no_draft` で素通り） |
| `chat_template_kwargs.enable_thinking` 透過 | ✓ | `--chat-template-args` はサーバ側指定 | 未確認 |
| `tool_choice` | 全種 ✓ | 未確認 | **無音で無視**（実測） |
| `usage` | ✓ | ✓ | ✓ |
| `finish_reason` `stop`/`length`/`tool_calls` | ✓ | ✓ | 未確認 |

## 5. 研究側との相違（記録）

- 探索: 研究側は `max_tokens=16384`・`timeout=900`・1 回再試行・`temperature: 0` に加えて記録制御ヘッダと `task_id` を送っていた。本リポの explore-v4 は後者 2 つを送らず、他は同一。
- lookup: 研究側は base tools（`dir_marker=True`）・`max_tokens=4096`・`temperature 0.7`・thinking 有効化 kwargs。本リポの lookup-pc は同一（kwargs は設定で省略可）。
- 研究側の測定 row はゲート拒否時も観測用 `answer`/`nonce` に attempted 値を残す。本リポの公開結果は出荷値を表すため、`harness_rejected=true` のとき両方を `None` にする。差分試験の研究側判定列も同じ出荷表現へ正規化する。
