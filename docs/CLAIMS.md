# CLAIMS.md — 主張表

本リポは「**出典照合・ファイル参照を補助する実験的クライアント**」である。以下は書かない:
「安定化」「安全」「検証済み」「病の解消」・RL 済みモデル一般への転移・未知問題への性能証明・
研究側の測定結果を本リポの実績として継承する記述。

下表の数値は**作者の非公開研究環境の凍結計器**（本リポの移植元）で 2026 年 9 月に測ったものであり、
本リポの移植版で再測定したものではない。移植版は差分試験（`docs/DIFFERENTIAL.md`）で要求列・判定列の
同値のみを保証する。「登録ラベル」は事前登録の凍結分岐の判定、「判断採用」は研究側での運用上の採否で、
両者は別物。

## 1. 結果表（checkpoint × 量子化 × タスク型 × 予算 × 構成）

| checkpoint／量子化／serving | タスク型 | 予算 | 構成（本リポの対応） | 主要値 | 登録ラベル | 判断採用 |
|---|---|---|---|---|---|---|
| Qwen3.6-35B-A3B base／NVFP4／vLLM thinking ON | 合成 lookup（alias／filtered_sum／index_routing／priority_chain・680 task-start state・2 draw） | round 6・max_tokens 4096・T 0.7 | **Pc**（`lookup-pc`） | Y 87.4%・非接地出荷 5.7%・捏造 nonce 受理 0 | （対照） | 既定 ON |
| 同上 | 同上 | 同上 | **C**（`lookup-c`）vs Pc | Y 93.2%・ΔY +5.7pt [+3.6, +7.8]・priority +21.2pt・非接地出荷 0・捏造受理 0・棄権 2.2% | **FAIL**（P1 閾・P3 対照条項＝登録側定義欠陥を開示・ラベル不変） | qwen3.6 base・数値 lookup 型で判断採用 |
| 同上 | 同上（保存出力の無走行再解析＋発火 35 行のみ live） | 同上 | **R-A／R-B**（`rules`）on C | R-A 抽出一致 29/29・R-B 発火 35・救済後正答 34/35・投影 Y 97.8% | **S0-GO・S1 RESCUE>ABSTAIN**（選択面＝確認主張ではない） | C 構成の一部として判断採用（数値 lookup 契約のみ） |
| 同上 | 実リポ lookup 質問 40（非公開 suite・8k 超 16） | round 6・max_tokens 16,384・T 0 | **tools v4**（`explore-v4`）vs v3 | task E 16/40 vs 10/40（ΔE +15pt）・8k 超 G 4/16 vs 0/16・round cap 8 vs 20 走・overflow 2 vs 6 | **INDETERMINATE**（ΔE ≥ +10 だが ΔG_8k +25 < +40） | 判断採用（baseline） |
| 同上 | 同上 | 同上 | 証拠パック finalize on v4 | ΔE ±0・ゲート通過の誤答 +3.7pt（v3 上） | **PRACTICAL-NULL／WORSENED** | **不採用**（本リポに含めない） |
| Qwen3.6-35B-A3B **Mercor**／NVFP4 W4A16／vLLM thinking ON **no-MTP** | 合成 lookup 680 × 2 draw | round 6・max_tokens 4096・T 0.7 | Pc（`lookup-pc`） | Y **91.2%**・捏造受理 2.1%・出荷接地誤り 5.2% | （対照） | `qwen36-mercor` プロファイルで ON |
| 同上 | 同上 | 同上 | C（`lookup-c`）vs Pc | ΔY +0.7pt [−1.2, +2.6]・捏造受理 2.1%→0・priority +6.2pt [−0.3, +12.6]・alias −2.4pt | **CEILING**（対照 ≥90%・TRANSFER 不成立） | **保留**（`qwen36-mercor` では OFF） |
| 同上 | 実リポ lookup 質問 40 | round 6・max_tokens 16,384・T 0 | tools v4 vs v3 | task E 13/40 vs 7/40（ΔE +15pt・paired CI [0.000, +0.300]）・overflow 6 vs 15・8k 超 G 7/16 vs 0/16 | **INDETERMINATE**（CI 下限 0） | 候補併記（`qwen36-mercor` で ON・方向一致のみ） |
| 同上 | 同上 | 同上 | トークン効率（記述） | lookup: 成功当たり Pc 7,037／C 6,971 token（同等）。探索: v3 186k → v4 140k（−25%）・総量は増 | 記述のみ | — |
| Qwen3.8-Flash-Next／NVFP4（RadixArk）／vLLM 2 台 TP2 thinking ON（fp8 KV） | 実リポ lookup 質問 40（非公開 suite・8k 超 16・**1 draw**） | round 6・max_tokens 16,384・T 0 | tools v4（`explore-v4`）vs v3 vs 素（回答契約なし） | 着地 47.5（素）／45.0（v3）／**70.0%**（v4）・task E 16→23/40（ΔE +17.5pt・CI [0.000, +0.350]）・8k 超 G 7→12/16・round cap 内 gold 到達済み 16→5・**H（出典書式違反）2→5 走（+7.5pt）** | WORSENED-1DRAW（H 点推定 > +2.5pt） | v4 を `qwen38-flash` の既定に採用（判断採用・H は出典行欠落／包装で捏造 0・出荷 0） |
| 同上 | 合成 lookup 160 state（4 型・1 draw） | round 6・max_tokens 4096・T 0.7 | C（`lookup-c`）vs Pc | Y Pc 117/160 vs C 121/160（ΔY +2.5pt）・自然着地 320/320・早期ゲート発火 0・棄権 0 | INDETERMINATE-1DRAW | C は `qwen38-flash` で ON（値形式契約と組で採用・単独効果は未確定） |
| 同上 | 保存 lookup 320 行（無走行再解析） | 同上 | 選択的 R-A（`selective_ra`） | Pc 117→135／C 121→136（+10.31pt）・発火 33/320・正→誤 0・非発火 287 行の出荷不変 | — | 既定 ON（`qwen38-flash`） |
| 同上 | 合成 lookup 160 state（新 state・1 draw） | 同上 | C＋選択的 R-A（対照）vs ＋値形式契約 1 文（`value_contract: digits-only`） | **Y 124→158/160（77.5→98.8%・ΔY +21.25pt・CI [+15.6, +27.5]）**・包装未解決 36→0・値誤答 0・非接地 0・R-A 発火 21→0・**棄権 +2（nonce 接頭辞 `nonce-` 欠落）**・model_calls +0.09・prompt token +10% | CONTRACT-SIGNAL-1DRAW | 既定 ON（`qwen38-flash`） |
| Qwen3.8-Flash-Next／NVFP4（Mia）／vLLM 単一 Spark thinking ON（bf16 KV） | 実リポ探索 120（非公開 suite v2・1 draw） | round 6・max_tokens 16,384・T 0 | 回答条件の 1 文（system 末尾）on v4 | H 2→7/120・E ±0.8pt・round cap −4.2pt | WORSENED-1DRAW | **不採用（本リポに含めない）** |
| 同上 | 同上 | 同上 | 検索結果の要約提示（tools v5） | E +1.7pt | INDETERMINATE | **不採用（含めない）** |
| 同上 | 保存探索 480 走（無走行再適用） | 同上 | 出典ゲート契約 v2（`citation_contract: v2`）vs v1 | 発火 11（backtick 10・二重引用符 1）・発火走は全て E 化・H 18→7・新規本文誤答 0・非発火 469 走は出荷オブジェクト全キー同一・長さ違反 1（216→206 字） | 判断採用（探索的評価） | 既定 ON（`qwen38-flash`）。qwen3.6 では未測定＝既定にしない |
| 同上 | 同一 120 問（v4＋ゲート v2） | 同上 | — | 記述: 正答（E）88→92/120（73.3→76.7%）・残る非正答 ≈28 のうち「検索語が証拠に届かない（言い換え）」≈17〜20・「証拠を手にして止まらない cap」7・空 stop 0〜2 | 記述のみ | — |

## 2. 明記する未測定・保留

- Mercor での **C 層は保留**（CEILING・alias −2.4pt）。`qwen36-mercor` プロファイルでは OFF。
- **R-A／R-B の Mercor live 救済は未実施**。保存行への無走行適用（S0-GO・R-B 59 行）まで。
- R-A／R-B は**名前が正答たり得るタスクには適用しない**（識別子名の出荷を非着地化する規則のため）。
- 探索面は base・Mercor とも **INDETERMINATE**（方向一致のみ。効果量の下限は詰まっていない）。
- 本リポの移植版による実機再測定は smoke（`docs/SMOKE.md`・記述のみ）まで。移植版の性能主張はない。
- 公開診断バッテリー（`battery/`）は合成であり、未知問題への性能証明ではない。
- qwen3.8 の全行は **1 draw**（再現性未確認）・配備 2 種の混在（fp8 KV 2 台 TP2／bf16 KV 単一 Spark）。
- 値形式契約・選択的 R-A・出典ゲート v2 の **qwen3.6 への転移は未測定**（qwen3.6 では静的文言が標的面で無効〜有害だった事前分布あり）。
- 探索面の「言い換え」失敗（≈17〜20/120）は本リポの範囲外（ハーネス 5 系統・外付け検索 5 方式で不成立）。
- 名前が正答たり得る型に `value_contract: digits-only`／`selective_ra` を使わない（棄権化する）。
- qwen3.8 探索面の cap（証拠到達後も止まらない）は v4 で半減したのみ（抑制）。

## 3. 反転・無効化条件

`docs/MONITORS.md` の計器で、素の応答（harness OFF）より害が増えた場合はそのプロファイルを無効化する。
研究側で観測済みの害の型: 名前類似度による配膳が誠実拒否を確信的誤答に転化する（権威転置）・字句ゲート充足のための空引用・着地を命じると実行捏造。本リポは配膳・着地命令・字句のみのゲートを含まない。

新規 3 機能の無効化条件（個別）:
- `value_contract`: 新配備で値誤答 ≥1／nonce 接頭辞欠落 Δ > +2.5pt／非接地出荷 ≥1／選択的 R-A 発火率 > 5%（契約が効いていない）。
- `selective_ra`: 正→誤 ≥1／発火率 > 20%（包装違反の増加＝上流の変化）。
- `citation_contract: v2`: unwrap 発火走で本文誤答 ≥1 または非接地出荷 ≥1 または unwrap 率 > 10%。
