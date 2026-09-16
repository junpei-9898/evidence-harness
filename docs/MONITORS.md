# MONITORS.md — 監視計器と無効化条件

各プロファイルは以下を毎走記録する。閾値を超えた場合はそのプロファイルを無効化して素の応答へ戻す。

| 計器 | 定義 | 無効化条件（案・確定） |
|---|---|---|
| 捏造 nonce 受理 | 出荷 answer の nonce が tool 結果本文に無い | ≥1 |
| 非接地出荷率 | 出荷 answer が tool 結果本文に無い割合 | 素の応答（harness OFF）より高い |
| 棄権率 | 出荷なし（gate 拒否・不能文）の割合 | 素の応答の棄権率＋10pt 超 |
| overflow 率 | `finish_reason=length` | 素の応答より高い |
| 追加呼出し | 救済 finalize・retrieval の回数 | 平均 >1.5/問 |
| 引用ゲート拒否率（explore） | `quote_not_verbatim`＋`source_not_fetched` | 記述のみ |
