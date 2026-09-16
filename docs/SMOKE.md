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

## Mercor: 未実施（載せ替え時期は作者判断）

## 移植性修正後の再 smoke（base・実機 1 台・直列）

| 経路 | 条件 | 結果 |
|---|---|---|
| バッテリー lookup 3 件（alias／priority／index） | 既定（thinking kwargs 送信）・`EVIDENCE_HARNESS_API_KEY` を設定（サーバは無視） | Y 3/3・接地 3/3・出荷非接地 0。着地は native 1／もう一度だけ答えさせる段 2。キー文字列は出力 JSON に現れない |
| CLI lookup 1 問 | `--chat-template-kwargs none`（kwargs 省略） | 正答 4820・根拠 ID 一致・native 着地・4 呼び出し。結果 JSON に kwargs の痕跡なし・最終ラウンド記録に reasoning あり |
