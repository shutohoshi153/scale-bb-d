# 金融庁 ESR 公表資料(BEL感応度デモの外部入力)

経済価値ベースのソルベンシー規制(ESR)の実装仕様を BEL 感応度デモ
(`../../../scripts/bel_demo/`)で再現するために取得した金融庁公表資料。
取得日: 2026-07-28。出典ページ:
https://www.fsa.go.jp/policy/economic_value-based_solvency/index.html

| ファイル | 内容 | 取得元 URL |
|---|---|---|
| `esr_yield_curve_tool_20260331.xlsx` | イールド・カーブ作成ツール(2026年3月末版)。パラメータシートの JPY 行(LOT=30、収束年限=60、UFR=3.8%、ゼロクーポン無リスク金利)を `build_esr_discount_curve.py` が読む | https://www.fsa.go.jp/policy/economic_value-based_solvency/20260323/20260331.xlsx |
| `esr_pillar1_kokuji74_20250723.pdf` | 1柱告示(令和7年金融庁告示第74号、2025-07-23 公布)。第56条 死亡リスク(日本 +12.5%)、第59・60条 罹患・障害リスク(健康事象発現時の一時金区分・長期・日本 発生率+20%)を参照 | https://www.fsa.go.jp/news/r7/hoken/20250723/07.pdf |
| `esr_pillar1_kokuji_20260323.pdf` | 1柱告示の一部改正(令和8年3月23日、2026-03-31 適用)。参考 | https://www.fsa.go.jp/news/r7/hoken/20260323/03.pdf |

注意: これらは金融庁の公表資料であり、本リポジトリのライセンスは及ばない。
規制対応の確実な理解には原典(告示・監督指針・Q&A)を参照のこと。
