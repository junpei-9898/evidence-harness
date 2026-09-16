# AGENTS.md — 委任規律

- 実装前に `docs/PORTING.md`・`docs/DIFFERENTIAL.md`・該当 `docs/SPEC_*.md` を読む。仕様の変更は先に docs を直し、コードはそれに従う。
- 研究側からの移植は**最小抽出＋アダプタ**。全面再設計・丸ごと vendoring・挙動の「改善」はしない。要求列 hash が変わる変更は差分試験で必ず露見する。
- 研究側の非公開ディレクトリ（測定 transcript・ログ・非公開 suite）は読まない。fixture は合成のみ。
- commit はオーケストレータが行う。委任実装者は commit しない。
- 新規テストは実在させる（stub 禁止）。`pytest -q`・`ruff check .`・`python scripts/leak_check.py` を通す。
- 絶対パス・実プロジェクト名・メールアドレスを書かない（漏出検査で止まる）。
