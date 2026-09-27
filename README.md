# evidence-harness

ローカル LLM に「リポジトリの中を調べて答えてもらう」とき、モデルは最後の数手でよく失敗します。
調べたのに答えを出さない。証拠にない ID を書いてしまう。検索で見つけた行を開けない。
evidence-harness は、こうした失敗を**モデルの外側から**補うクライアントです。
OpenAI 互換の chat API に対して動き、モデル自体には手を入れません。

> Experimental client-side harness that assists source-citing and file-reference behaviour of
> OpenAI-compatible chat models. Model-agnostic; ships no weights.

## どんな失敗が起きるのか

30B 級のローカルモデルにファイル読み取りツールを渡すと、探すこと自体はだいたいできます。
失敗するのは、そのあとです。

**1. 調べたのに、最後の答えを出さない**
必要なファイルは読み終えているのに、答えを言わずに探索を続け、ラウンド上限で止まります。
モデルの思考メモを見ると、答えの下書きはすでに書かれています。「もう答えていい」と決める力が弱いのです。

**2. 証拠にない情報を、それらしく書く**
答えの根拠として ID や値を添えるのですが、その ID が実際に読んだ本文のどこにも無いことがあります。
形式は守れても、自分の書いた値が証拠と対応しているかを確認しません。

**3. 長い文書の奥にたどり着けない**
検索（grep）で該当行は見つかるのに、その場所を開けません。ファイルの先頭 8,000 文字だけ読んで諦めます。
検索結果の「行番号」と、読み取りツールの「文字位置」が別の数え方で、橋渡しを間違えるためです。

**1'. 値の答えを、散文や識別子っぽい文字列で包んで出す（Qwen3.8 で新たに確認）**
値そのものは合っているのに、そのまま出荷せず、説明文や識別子らしき文字列に混ぜて書いてしまいます。
answer 欄が数字だけであるべき問題でこれが起きると、後段の照合が値を取り出せず、正答が不正解として扱われます。

## このハーネスがすること

**1 に対して: 下書きを拾い、拾えなければもう一度だけ答えさせる**
ラウンド上限で止まったとき、最終ラウンドの思考メモに答えの下書きが 1 つだけあればそれを採用します。
無ければ、これまでの会話履歴を捨て、「質問」と「読んだファイルの本文」だけを渡して、1 回だけ答えを書かせます。

**2 に対して: 証拠に無い答えは出さない**
答えに添えられた ID や引用が、実際にツールが返した本文の中に文字どおり存在するかを機械的に照合します。
無ければその答えは捨て、「取得した証拠では確認できない」と返します。
さらに厳しくしたい場合は、照合に失敗した時点で該当箇所を再取得して答え直させる追加層を有効にできます。

引用が backtick や二重引用符でもう一段包まれているだけで、この照合が誤って引用を拒否することがありました。
出典ゲート契約 v2 は、照合の前に外側の対称な一層（backtick 1 組、または二重引用符 1 組）だけを剥がしてから
再照合します。出荷される引用の文字列そのものは変えません。

**3 に対して: 検索結果から直接その場所を開けるようにする**
grep の結果に「行番号」と「文字位置」の両方を付け、読み取りツールがどちらでも開けるようにします。
8,000 文字ずつページをめくれるので、長い文書の奥まで読めます。

**1' に対して: 答えの形式を契約で縛り、抽出規則は候補が一意なときだけ使う**
lookup で 1 つの値を答えさせるとき、「answer 欄は ASCII の数字だけの文字列であること」という 1 文を
system プロンプトの末尾に追加できます。これに、出荷しようとした答えの文字列に純数字のトークンがちょうど 1 つだけ含まれる場合に限って
その値へ差し替える、絞り込み版の抽出規則（選択的 R-A）を組み合わせられます。数字だけの答えや、候補が複数・ゼロの答えは触りません。
名前が正答になる問題ではどちらも使いません（識別子の出荷を止めてしまうため）。

## どれくらい効いたか

### (a) Qwen3.6-35B-A3B（base／Mercor）

Qwen3.6-35B-A3B（4bit 量子化・vLLM）で、素のモデルと、ハーネスを付けた場合を比べました。
「base」は公開されている元のモデル、「Mercor」は同じモデルに追加学習を施した公開版です。

| 失敗 | 何を数えたか | base | Mercor |
|---|---|---|---|
| 1. 答えを出さない | 正答率（ハーネス前 → 後） | 71.1% → **87.4%** | 51.0% → **91.2%** |
| 2. 証拠にない ID | 証拠に無い ID を含む答えを通した割合 | 5.7% → **0%** | 2.1% → **0%** |
| 3. 奥に届かない | 先頭 8,000 文字より奥にある根拠を 2 回とも取れた課題 | 0/16 → **4/16** | 0/16 → **7/16** |
| 3. 奥に届かない | ラウンド上限で止まった回数（80 回中） | 20 → **8** | 34 → **26** |
| 3. 奥に届かない | 出力の長さ上限に当たった回数（80 回中） | 6 → **2** | 15 → **6** |
| 効率 | 正答 1 件あたりに使ったトークン | **18% 減** | **25% 減** |

条件: 1 と 2 は合成した 680 問を 2 回ずつ（1,360 回）。3 は実在リポジトリに対する 40 問を 2 回ずつ（80 回）。
1 の「前」は同じ実行ログの中でハーネスが介入する前の答え、「後」は介入後の答えです。
探索面（3）の改善は統計的にはまだ確定していません（方向は両モデルで一致）。
2 の追加層は Mercor では全体の正答率をほとんど動かさず、一部の問題型で少し悪化したため、Mercor 向けの既定では無効にしています。

### (b) Qwen3.8-Flash-Next

Qwen3.8-Flash-Next（NVFP4 量子化・vLLM・thinking ON）でも同じように比べました。
**値を答える面（1'・2）は合成 160 問・1 draw（再現性は未確認）、探す面（1・3）は実在リポジトリへの
40 問・1 draw、引用の包装は保存済み 480 走への無走行再適用のうち 120 問での記述です。**

| 失敗 | 何を数えたか | 前 → 後 |
|---|---|---|
| 1'. 値を散文や識別子で包んで答える | 正答率（160 問・1 draw） | 77.5% → **98.8%** |
| 3. 読む先を外す（grep 行番号を文字位置に渡す） | 取り違え回数／着地率（40 問・1 draw） | 8 回 → **0**／47.5% → **70.0%** |
| 引用を backtick／引用符で包んでゲートに落ちる | 包装で落ちた回答（120 問） | 5 → **0〜1** |
| 証拠を手にしても探索を止めない | round 上限で終わった走（40 問） | 素 21/40 → v4 12/40（抑制のみ） |

副作用: 値形式契約は nonce の接頭辞を落として棄権させることがあります（160 問中 2 件）。
探索面の着地率改善（47.5%→70.0%）と同じ構成で、出典書式に違反する答え（引用ゲートに落ちる形の誤り）
も 2→5 走に増えました。捏造や本文にない値の出荷は増えていません。研究側の事前登録された判定はこの
構成で `WORSENED-1DRAW`（出典書式違反の増加が判定基準を超えたため）ですが、運用上は `qwen38-flash`
の既定として採用されています。**「登録ラベル」（事前登録された判定）と「判断採用」（運用上の採否）は
別物として扱っています**。詳しい条件と両方のラベルは `docs/CLAIMS.md` にあります。

## まだ直っていないこと

- **証拠は正しく読んだのに、値を選び間違える**答えは止められません。ハーネスは「証拠に無いもの」を止める装置で、「証拠の中から間違ったものを選ぶ」ことには効きません。Mercor では優先順位を問う型の問題でこの誤りが 17% 残ります。
- 同じ質問でも実行ごとに結果が変わります（量子化と並列実行の影響）。探索 40 問のうち 14 問は 2 回のうち片方だけ成功でした。
- 2 の追加層は「答えない」判断を増やします。捏造ゼロと正答率の間にはトレードオフがあります。
- 答えがサービス名のような「名前」になる問題では、答えは正しいのに根拠 ID を捏造する例が出ます。数値向けの補助規則（値形式契約・選択的 R-A）はこの型には使いません（使うと棄権が増えます）。
- Qwen3.8 でも、検索語が証拠の言い回しに届かない失敗が残ります（探索 120 問中 ≈17〜20 問）。ハーネス側の複数の系統と外付け検索を試しましたが改善せず、本リポの範囲外としています。
- Qwen3.8 の「証拠を手にしても探索を止めない」cap は、tools v4 でおよそ半分に減るだけで無くなりません。
- Qwen3.8 の空 stop（答えを出さずに終わる走）は探索 120 問中 0〜2 件ありますが、原因は切り分けられていません。
- 値形式契約・選択的 R-A・出典ゲート契約 v2 の Qwen3.6 への転移は測っていません。Qwen3.6 では別の静的な文言がむしろ標的面を悪化させた経緯があるため、既定では有効にしていません。
- 効果を確認しているのは Qwen3.6-35B-A3B と Qwen3.8-Flash-Next です（Qwen3.8 の数値は 1 draw・再現性は未確認）。他のモデルでも動きますが、効くかどうかは測ってから書きます。

## 使えるモデル

コードにモデル名の分岐はありません。サーバが次を満たせば動きます。

| サーバに必要なこと | 必須か |
|---|---|
| chat completions API で `tools` を受け取り、`tool_calls` を返し、`role: "tool"` のメッセージを受け付ける | 必須 |
| 使用トークン数（`usage`）を返す | あると監視に使える |
| 思考メモ（`reasoning`）を分けて返す | あると「下書き拾い」が働く。無くても「もう一度答えさせる」経路は働く |
| thinking 制御 kwargs | 任意。lookup は既定で Qwen 系の `enable_thinking` を送る。不要なら `none` で省略できる |
| `finish_reason` に `stop` / `length` / `tool_calls` を返す | あると長さ上限の検知に使える |

vLLM・mlx_lm.server・Ollama で動作を確認しています。

測定済みモデル（結果は `docs/CLAIMS.md` に判定込みで記載しています）:

| checkpoint | 量子化・serving | プロファイル名 | recipe | 測定の深さ |
|---|---|---|---|---|
| Qwen3.6-35B-A3B base | NVFP4・vLLM | `qwen36-base` | `recipes/qwen36-base-nvfp4-vllm.md` | 2 draw |
| Qwen3.6-35B-A3B Mercor | NVFP4 W4A16（no-MTP）・vLLM | `qwen36-mercor` | `recipes/qwen36-mercor-nvfp4-vllm.md` | 2 draw |
| Qwen3.8-Flash-Next（探索面） | NVFP4・単一 Spark・vLLM | `qwen38-flash` | `recipes/qwen38-flash-nvfp4-vllm.md` | 1 draw |
| Qwen3.8-Flash-Next（値を答える面） | NVFP4・2 台 TP2・vLLM | `qwen38-flash` | `recipes/qwen38-flash-nvfp4-vllm.md` | 1 draw |
| DeepSeek V4 Flash | — | — | — | OpenAI 互換で動作のみ確認・効果は未測定 |
| GLM 5.3 Flash | — | — | — | OpenAI 互換で動作のみ確認・効果は未測定 |

Qwen3.8-Flash-Next の 2 行は同じ checkpoint 名でも量子化元の配備が異なります（詳細は
`recipes/qwen38-flash-nvfp4-vllm.md` の「配備差の開示」）。

## 使い方

```
uv venv --python 3.12 .venv && uv pip install --python .venv/bin/python -e '.[dev]'
```

認証が必要な場合は `--api-key` または環境変数 `EVIDENCE_HARNESS_API_KEY` を使います。
`--dry-run` を付けるとモデルを呼ばずに構成だけ確認できます。

### Qwen3.6-35B-A3B base

```
# 探索（出典・引用つき）
.venv/bin/evidence-harness explore --base-url http://HOST:PORT/v1 --model NAME --workdir DIR \
  --question "..." --profile qwen36-base --out result.json

# 値を 1 つ答えさせる
.venv/bin/evidence-harness lookup --base-url http://HOST:PORT/v1 --model NAME --workdir DIR \
  --question "..." --profile qwen36-base --out result.json
```

### Qwen3.6-35B-A3B Mercor

```
.venv/bin/evidence-harness explore --base-url http://HOST:PORT/v1 --model NAME --workdir DIR \
  --question "..." --profile qwen36-mercor --out result.json

.venv/bin/evidence-harness lookup --base-url http://HOST:PORT/v1 --model NAME --workdir DIR \
  --question "..." --profile qwen36-mercor --out result.json
```

### Qwen3.8-Flash-Next

```
.venv/bin/evidence-harness explore --base-url http://HOST:PORT/v1 --model NAME --workdir DIR \
  --question "..." --profile qwen38-flash --out result.json

.venv/bin/evidence-harness lookup --base-url http://HOST:PORT/v1 --model NAME --workdir DIR \
  --question "..." --profile qwen38-flash --out result.json
```

`qwen38-flash` は lookup 内部で `lookup-c`（照合に失敗したら再取得して答え直す層つき）を使います。
`qwen36-base`／`qwen36-mercor` は `lookup-pc`（下書き拾い＋再答えさせのみ）です。

いずれのプロファイルでも `--citation-contract v1|v2`（explore のみ）・`--value-contract none|digits-only`・
`--selective-ra`/`--no-selective-ra`（lookup のみ）でプロファイルの既定を上書きできます。
lookup の thinking 設定は `--chat-template-kwargs '{"enable_thinking":false}'` で上書きし、
`none` で送信を省略できます。

| プロファイル | 用途 | 既定 |
|---|---|---|
| `explore-v4` | リポジトリを探索し、`出典:`／`引用:` の 2 行付きで答える。引用が本文と一致しない答えは出さない | 有効 |
| `lookup-pc` | 1 つの値を `{"answer", "nonce"}` の形で答える。下書き拾いと、もう一度だけ答えさせる救済を含む | 有効 |
| `lookup-c` | `lookup-pc` に「照合に失敗したら再取得して答え直す」層を重ねる。捏造 ID をゼロにしたいときに | 無効 |
| `rules` | 数値を答える問題向けの決定論的な後処理。名前を答える問題には使わない | 無効 |

新しく増えた 3 つの鍵と、checkpoint 別プロファイルでの既定 ON／OFF:

| 鍵 | 意味 | `qwen36-base` | `qwen36-mercor` | `qwen38-flash` |
|---|---|---|---|---|
| `citation_contract` | 出典ゲートの照合方式。`v1`＝素の照合、`v2`＝外側の backtick／引用符を 1 層だけ剥がしてから照合 | `v1` | `v1` | `v2` |
| `value_contract` | lookup の answer 欄の形式を縛る 1 文。`none`／`digits-only`（ASCII 数字のみ） | `none` | `none` | `digits-only` |
| `selective_ra` | 出荷しようとした答えに純数字トークンがちょうど 1 つあるときだけその値へ差し替える抽出規則 | `false` | `false` | `true` |

`profiles/*.yaml` はモデルごとの既定値の束です。`qwen36-base.yaml`／`qwen36-mercor.yaml`／`qwen38-flash.yaml`
を参照してください。

## 診断セット

`battery/` に、自分の環境でモデルの失敗の出方を測るための合成問題と採点器があります。
lookup 6 種、長い合成リポジトリの探索、対照 3 種（証拠なし・紛らわしい出典・名前が答え）、証拠差し替え A/B の 4 セットです。

```
python -m battery.run --base-url URL --model NAME --profile lookup-pc --set lookup --seed 0 --n 8 --out out.jsonl
```

seed を固定すれば同じ問題が再現します。正解は採点器だけが持ち、モデルが読むディレクトリには置きません。
新しいモデルを載せる際の具体的な手順は次節にまとめています。これは自分の環境での診断であり、
未知の問題に対する性能の証明ではありません。

## 新しいモデルを載せる手順

1. 上の 4 セット（lookup・探索・対照・証拠差し替え A/B）を「素のモデル」と「ハーネス付き」の両方で回し、
   答えない割合と証拠に無い答えの割合が素のモデルより悪化していないことを確認します。
2. 確認できたら `profiles/<checkpoint>.yaml` を作ります。既定は全部 OFF
   （`value_contract: none`・`selective_ra: false`・`citation_contract: v1`・`rules: false`）から始め、
   効果を確認したものだけ ON にします。
3. 自分の環境で測った値を `docs/CLAIMS.md` に新しい行として追記します。1 回しか測っていない場合は
   その旨（1 draw）を書きます。

## 文書

- `docs/CLAIMS.md` — 何を主張し何を主張しないか。モデルごとの結果表と研究側の判定ラベル
- `docs/MONITORS.md` — 運用中に見る指標と、無効化する条件
- `docs/SPEC_explore.md`・`docs/SPEC_lookup.md` — 各プロファイルの動きの詳細
- `docs/PORTING.md` — 移植元（研究用コード）との対応表
- `docs/DIFFERENTIAL.md` — 移植元と同じ動きをすることの検証方法
- `docs/SMOKE.md` — 実機での動作確認記録
- `recipes/` — 各モデルの vLLM 起動レシピと開示（`qwen36-base-nvfp4-vllm.md`／`qwen36-mercor-nvfp4-vllm.md`／`qwen38-flash-nvfp4-vllm.md`）
- `profiles/*.yaml` — モデルごとの既定値（`qwen36-base.yaml`／`qwen36-mercor.yaml`／`qwen38-flash.yaml` ほか）

## ライセンス

MIT（`LICENSE`・`NOTICE`）。参照している公開モデルの重みは、それぞれの配布元のライセンスに従います。
