# 公開診断バッテリー

`battery/` は、`evidence-harness` の探索・lookup プロファイルを合成データで診断するための
独立パッケージです。公開診断は未知問題への性能証明ではありません。

## セット

- `lookup`: `alias_resolution`、`priority_chain`、`index_routing`、`filtered_sum`、
  `single_lookup`、`two_file_join` の 6 型を順番に生成します。
- `explore`: 10〜40 ファイルの架空リポジトリを生成します。偶数番の item は正解文を
  8,000 文字より深い位置に、奇数番の item は浅い位置に置きます。別ファイルに似た語の
  distractor を置きます。
- `controls`: `no_evidence`（棄権が正解）、`confusing_source`（権威文書が正解）、
  `name_answer`（識別子名が正答）の 3 型です。`name_answer` は R-A/R-B を名前が正答に
  なり得る課題へ適用してはいけないことを確認する診断です。
- `supplied`: 一般的な既定値と異なる値を証拠が示す `counter_default` と、架空名詞の属性を
  問う `fictional` を交互に生成します。各 item は証拠だけを差し替えた A/B ペアです。

同じ seed、件数、セットからは常に同じ item が生成されます。`--n` は item 数で、既定は 8、
`--seed` は開始 seed で、既定は 0 です。lookup の 6 型と controls の 3 型は型を一巡してから
seed を 1 増やします。explore と supplied は item ごとに seed を 1 増やします。

## 実行

```console
python -m battery.run \
  --base-url http://127.0.0.1:8000/v1 \
  --model local-model \
  --profile lookup-pc \
  --set lookup \
  --seed 0 \
  --n 8 \
  --out results.jsonl
```

`explore` セットには `--profile explore-v4` を使います。`lookup`、`controls`、`supplied` には
`lookup-pc` または `lookup-c` を使います。実行は逐次で、1 item が完了するたびに JSONL へ
追記します。`--resume` を付けると、出力済みの item ID を飛ばして続行します。

生成 item の `gold` は採点処理のメモリ内だけで参照します。モデル用の一時作業ディレクトリへ
展開するのは `files` の本文だけで、gold、質問、採点値をファイルとして書きません。出力 JSONL
にも gold 自体は保存せず、item 識別情報、プロファイル結果、採点結果だけを保存します。
