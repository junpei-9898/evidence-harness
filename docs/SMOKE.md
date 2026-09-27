# SMOKE.md — 実機 smoke の記録（記述のみ・性能主張なし）

移植版 CLI を記載レシピどおりに起動したサーバに対して 1 問ずつ流し、要求が通り・tools が往復し・
ゲート／救済が動くことを確認する。合成 workdir（数ファイル・gold を含む）を使う。値の正否は記録するが主張しない。

## base: Qwen3.6-35B-A3B NVFP4（vLLM・thinking ON・`recipes/qwen36-base-nvfp4-vllm.md`）— 2026-09-15

| プロファイル | 問い（合成） | 結果 | 経路 | 呼出し | usage |
|---|---|---|---|---|---|
| explore-v4（max_tokens 16,384・T 0） | 「orchard sync worker はアップロード失敗時に最大何回リトライするか」（gold は深い md の 18,533 文字目と `worker.py` の定数に重複配置） | 正答 7・`出典: src/orchard/worker.py`・引用は取得済み本文と逐語一致 → **gate passed** | glob×3 → read×2 → 着地（3 ラウンド・stall 非発火） | 3 | prompt 4,662／completion 939 |
| lookup-pc（max_tokens 4,096・T 0.7） | 「storage shard_limit の現在値」（legacy に旧値 1200・active に 4820＋`nonce-k7x2m9`） | 出荷 `{"answer":"4820","nonce":"k7x2m9"}`・nonce は read 本文に逐語 → 受理 | grep → read → **native は JSON 契約に従わず平文 `4820` で stop**（`final_answer` 不成立・B3 は `not_cap`）→ **救済 finalize が 1 回で契約どおり着地**（`landing_source=finalizer`・`extra_calls=1`） | 4 | prompt 2,316／completion 744 |

観察: lookup の質問文に「値だけ答えよ」と書いたため native が system の JSON 契約と衝突した（問い側の誤り）。
救済 finalize が想定どおり契約違反の着地を JSON へ回収し、nonce 接地も通った。移植版の transport／tools 往復／
ゲート／救済経路が vLLM 実機で動くことを確認した（同値は差分試験が担保・本表は動作確認）。

### base: 公開バッテリー既定構成（`--seed 0 --n 8`・2026-09-15・逐次・edge ノード 2 台に面を分けて実行）

| セット | プロファイル | 結果（記述） |
|---|---|---|
| explore（deep 4／shallow 4） | explore-v4 | E 8/8・gate passed 8/8・棄権 0・エラー 0 |
| lookup（6 型） | lookup-pc | Y 8/8・nonce 接地 8/8・非接地出荷 0・エラー 0 |
| controls（証拠なし 3／紛らわしい出典 3／名前正答 2） | lookup-pc | 証拠なし 3/3 棄権（正）・紛らわしい出典 3/3 正（権威側の値）・**名前正答 2 件は 1 件が正答だが nonce を捏造（`12345`）して出荷＝`shipped_ungrounded`・1 件は捏造 nonce（`0`）→救済 finalize→`nonce_ungrounded` で棄権** |
| supplied（counter-default 4／fictional 4・A/B 各 8） | lookup-pc | A/B とも証拠追随 16/16・prior_pull 0 |

観察: 名前正答型で「答えは正しいが nonce を捏造して出荷する」行が出た。これは研究側で C 層（`lookup-c`）が
捏造受理を 0 にした対象と同じ型で、Pc 単独では素通りする（Pc は native 着地にゲートを持たない）。診断バッテリーの
対照がこの型を可視化できることの確認であり、性能主張ではない。バッテリーの `correct` は answer のみで判定し、
接地は `grounded`／`shipped_ungrounded` で別に出す。

## Qwen3.8-Flash-Next: `qwen38-flash` プロファイル（vLLM・単一 Spark・thinking ON・`recipes/qwen38-flash-nvfp4-vllm.md` A）— 2026-09-28

移植版 CLI（S5 の checkpoint プロファイル解決を含む）を実機に直列で流した。動作確認であり性能主張ではない。

| プロファイル | 問い（合成） | 結果 | 経路 | 呼出し | usage |
|---|---|---|---|---|---|
| explore（`qwen38-flash`＝explore-v4＋`citation_contract: v2`） | 「orchard sync worker はアップロード失敗時に最大何回リトライするか」（gold は `worker.py` の定数と 21,000 字超の runbook 末尾に重複配置） | 正答 7・`出典: src/orchard/worker.py`・引用は逐語一致 → **gate passed（`quote_match_form=raw`・契約 v2.0-unwrap1 を結果に記録）** | glob → grep → read → 着地（3 ラウンド・stall は観測のみ） | 4 | prompt 5,765／completion 425・17 s |
| lookup（`qwen38-flash`＝lookup-c＋`value_contract: digits-only`＋`selective_ra`） | 「active 設定の storage shard_limit の現在値と隣の nonce」（legacy に旧値 1200・active に 4820＋`nonce-k7x2m9`） | 出荷 `{"answer":"4820","nonce":"nonce-k7x2m9"}`・native 着地・strict 通過・`value_contract.sha256` が凍結 digest と一致・選択的 R-A は `bare_digits` で不発 | glob → grep×2 → read → 着地 | 3 | prompt 2,549／completion 247・7.7 s |

### 公開バッテリー既定構成（`--profile qwen38-flash --seed 0 --n 8`・直列・約 37 分）

| セット | 結果（記述） |
|---|---|
| lookup（6 型） | Y 8/8・nonce 接地 8/8・nonce 接頭辞欠落 0・非接地出荷 0・選択的 R-A 発火 0（全件 bare_digits）・着地は native 7／下書き拾い 1・エラー 0 |
| controls | 証拠なし 3/3 棄権（正・救済 finalize→`unparseable_final_answer`）・紛らわしい出典 3/3 正（権威側の値）・**名前正答 2 件は 1 件棄権・1 件が数値 `28` を出荷（誤答・接地はしている）** |
| supplied（証拠差し替え A/B） | counter-default 4/4 が A/B とも証拠追随・prior_pull 0。**fictional（名前が正答）4 件は 1 件のみ A/B 両追随**。残りは棄権 3 セル・数値化 2 セル（`27`、および正答名 `verdant` を **ASCII コード列 `11810111410097110116` に符号化して出荷**） |
| explore（deep 4／shallow 4） | E 7/8・gate passed 7（全て raw 一致・unwrap 発火 0）・1 件が round 上限（6）に達し `missing_source`・overflow 0・エラー 0 |

観察:
- 値形式契約（digits-only）を**名前が正答になる型に当てると害が出る**ことが対照で再現した。棄権に加えて、名前を数字列に符号化して契約を満たす行動（1 件）が出た。これは「数字だけ」という契約を字義どおりに満たす Goodhart で、`docs/CLAIMS.md` §2 の「名前型には使わない」注意の実例。バッテリーの対照はこの型を可視化できる。
- 探索面は round 上限 1/8（証拠に到達しないまま探索継続）が出た。研究側で観測済みの cap の型で、ハーネスは介入しない（記録のみ）。
- 移植版の transport／tools 往復／契約つき system／選択的 R-A／ゲート v2 の経路が vLLM 実機で動くことを確認した（同値は差分試験が担保）。

## Mercor: 未実施（載せ替え時期は作者判断）

## 移植性修正後の再 smoke（base・実機 1 台・直列）

| 経路 | 条件 | 結果 |
|---|---|---|
| バッテリー lookup 3 件（alias／priority／index） | 既定（thinking kwargs 送信）・`EVIDENCE_HARNESS_API_KEY` を設定（サーバは無視） | Y 3/3・接地 3/3・出荷非接地 0。着地は native 1／もう一度だけ答えさせる段 2。キー文字列は出力 JSON に現れない |
| CLI lookup 1 問 | `--chat-template-kwargs none`（kwargs 省略） | 正答 4820・根拠 ID 一致・native 着地・4 呼び出し。結果 JSON に kwargs の痕跡なし・最終ラウンド記録に reasoning あり |
