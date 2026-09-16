# SPEC_lookup.md — lookup プロファイル `lookup-pc`（既定）／`lookup-c`（OFF）／`rules`（OFF）

用途: 作業ディレクトリ内のファイルから**1 つの値**を探して答える型の質問。出力契約は
`{"answer": "<値>", "nonce": "<取得した tool 結果本文に逐語で含まれる文字列>"}` の JSON 1 個。
nonce が tool 結果本文（`result.content`・メタデータ除外）に含まれない回答は出荷しない。

## 1. `lookup-pc`（研究側 Pc＝B3＋救済 finalize）

1. `messages = [system=SYSTEM_LOOKUP, user=question]`・tools は base 契約（`read_file(path)`／`glob(pattern)`／`grep(pattern, path)`・glob は `dir_marker=True`）。
2. 最大 6 ラウンド、payload `{"model","messages","tools","temperature":0.7（既定・上書き可）,"max_tokens":4096,"chat_template_kwargs":{"enable_thinking":true}}`。`chat_template_kwargs` は既定 `{"enable_thinking":true}` で、設定により省略できる。
3. tool_calls が無いラウンドで `final_answer(message)`（content 中の最初の `{answer,nonce}` JSON）を読む。得られれば `landing_source="native"` で終了。
4. 6 ラウンド内に着地しない（`_structural_cap`: 最終 message が tool_calls あり／content 空／`finish_reason!="stop"`）とき **B3**: 最終ラウンドの `reasoning` から `{answer,nonce}` の草稿を全て拾い、**唯一**の草稿で・複合回答でなく・nonce が tool 結果本文に含まれるものだけ採択（`b3_reason`: `not_cap|no_draft|conflicting_drafts|compound_answer|nonce_ungrounded`）。採択後 `gate_final`（nonce 逐語接地）で再確認。
5. まだ無ければ **救済 finalize**（7 回目の呼び出し・`extra_calls+=1`）: 履歴を捨て `[system, user = question + "\n\nEvidence collected (path: content):\n" + 各 read_file の path:content]` を tools なしで送る。返答を `final_answer` → `gate_final`（`unparseable_final_answer|empty_nonce|nonce_ungrounded` で拒否）。
6. 拒否時は `harness_rejected=True, reject_reason` を残し、出荷 answer は None（棄権として扱う）。

## 2. `lookup-c`（OFF・Pc の上に重ねる）

- native 着地の nonce が接地していないとき**早期ゲート**発火 → retrieval（合成 grep `{"pattern":"nonce"}` → 未読候補パス ≤2 を合成 read）→ 履歴 reset finalize（tools なし・上記 5 と同じ user 文）→ `strict_gate`（nonce が `nonce-[a-z0-9]+` の**完全一致トークン**として tool 結果に存在・answer が nonce 形でない）。
- native 着地が接地していれば `strict_gate` のみ。自然非着地は B3 → 救済 finalize → `strict_gate`。
- 研究側の適用範囲は qwen3.6 base・数値 lookup 型のみ。Mercor は保留（`docs/CLAIMS.md`）。

## 3. `rules`（OFF・数値 lookup 契約のタスクのみ）

- R-A: answer が純数字なら採用。区切りで分割して純数字トークンが唯一ならそれを採用（`unique_digit_token`）。0 件／複数は不採用。
- R-B: R-A 不採用時、answer の全トークンが「pack パス・read 済みパス・read 本文の `key=`/`key:` キー・markdown 見出し」由来の識別子と一致するなら**非着地化**（識別子名を答えとして出荷しない）。
- 名前が正答たり得る型には適用しない（研究側の開示）。byte 凍結・digest は `docs/PORTING.md` §1。
- CLI の `--rules` 指定時だけ `complete()` を出荷 answer に適用し、判定辞書を結果の `rules` に残す。

## 4. 監視計器

非接地出荷率（gate 通過後の answer が tool 本文に無い）・捏造 nonce 受理（0 が要件）・棄権率・overflow 率・追加呼出し数（`extra_calls`）・usage 合計。反転条件は `docs/MONITORS.md`。
