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

## 2. 明記する未測定・保留

- Mercor での **C 層は保留**（CEILING・alias −2.4pt）。`qwen36-mercor` プロファイルでは OFF。
- **R-A／R-B の Mercor live 救済は未実施**。保存行への無走行適用（S0-GO・R-B 59 行）まで。
- R-A／R-B は**名前が正答たり得るタスクには適用しない**（識別子名の出荷を非着地化する規則のため）。
- 探索面は base・Mercor とも **INDETERMINATE**（方向一致のみ。効果量の下限は詰まっていない）。
- 本リポの移植版による実機再測定は smoke（`docs/SMOKE.md`・記述のみ）まで。移植版の性能主張はない。
- 公開診断バッテリー（`battery/`）は合成であり、未知問題への性能証明ではない。

## 3. 反転・無効化条件

`docs/MONITORS.md` の計器で、素の応答（harness OFF）より害が増えた場合はそのプロファイルを無効化する。
研究側で観測済みの害の型: 名前類似度による配膳が誠実拒否を確信的誤答に転化する（権威転置）・字句ゲート充足のための空引用・着地を命じると実行捏造。本リポは配膳・着地命令・字句のみのゲートを含まない。
