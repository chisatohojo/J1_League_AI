# J.LEAGUE match-level advanced stats research

調査日: 2026-09-20 JST  
対象: J1、公式サイト優先。大量取得・collector実装は行っていない。

## 結論

- **xG: C**。公式で確認できたのはクラブのシーズン集計で、match-levelのhome/away最終値、PK・Own Goalを含む定義、match ID対応を確認できなかった。
- **Shots on Target: B**。J.LEAGUE.jpの試合ページにhome/awayの最終Match Stats項目が表示されることを2020、2024、2025で確認した。ただし2015〜2019の同一方式・全試合coverageは未確認。
- **Possession: B**。同じ試合ページにhome/awayのPossession (%)項目が表示されることを2020〜2024のサンプルで確認したが、過去シーズンを含む全試合coverageと値の丸め規則は未確認。

「確認できない」は欠損を意味せず、今回の少数サンプルだけではcollectorの全期間完全性を保証できないという意味である。

## 指標別整理

| Stat | Official source | Match-level available | Home/Away available | Final value available | Oldest confirmed season | Newest confirmed season | 2020 coverage | 2021 coverage | 2022 coverage | 2023 coverage | 2024 coverage | 2025 coverage | Structured endpoint | Match-ID mapping | Definition notes | Missing-data risk | Collector feasibility | Classification |
|---|---|---|---|---|---:|---:|---|---|---|---|---|---|---|---|---|---|---|---|
| xG | J.LEAGUE.jp J1 Club Stats / Expected Goals | **No confirmed match page value**。season aggregateのみ確認 | aggregateはclub単位。match home/awayは未確認 | 未確認 | 2024 | 2025 | aggregate確認 | 未確認 | 未確認 | 未確認 | aggregate確認 | aggregate確認 | 公開match-level endpoint未確認 | club season URLのため既存match_idへ安定対応不可 | PK込み/除外、Own Goal、provider、モデル変更を公式表示だけでは確定できない | match単位欠損・定義不明 | season aggregate用途に限る。rolling用途は不可 | **C** |
| Shots on Target | J.LEAGUE.jp match `/stats/` | **Yes: sample confirmed** | Yes。Match Statsの左右2チーム列 | Yes。試合終了後のFull Time/Match Stats欄 | 2020 | 2025 | 確認（2020-08-15 sample） | 確認（2021-08-25 sample） | 確認（2022-10-08 sample） | 2023 match page search resultでStats導線確認、値の代表sample未採取 | 確認（2024-05-15 sample） | 確認（2025-08-23 sample） | HTML本文として取得可能。公開JSON/XHR endpointは今回未特定 | `https://www.jleague.jp/en/match/j1/YYYY/MMDDNN/stats/` のmatch slugを既存match_id対応表へ結合する必要あり。Data Siteの`match_card_id`との直接同一性は未確認 | Data SiteのSHとは別項目。Shots on Targetとして独立表示 | 古いseason、延期/再試合、stats欄欠落の全件確認が必要 | 2020〜2025のprototype候補。2015〜2019まで遡るには追加sample検証が必要 | **B** |
| Possession | J.LEAGUE.jp match `/stats/` | **Yes: sample confirmed** | Yes。Possession (%)のhome/away値 | Yes。試合終了後のMatch Stats欄として表示される | 2020 | 2025 | 確認（2020-08-15、2020-07-08 samples） | 確認（2021-08-25 sample） | 確認（2022-10-08 sample） | 2023 match pageのStats導線を確認、全値の代表sampleは未採取 | 確認（2024-05-15 sample） | 確認（2025 pageでMatch Stats構造確認） | HTML本文として取得可能。公開JSON/XHR endpointは今回未特定 | J.LEAGUE.jp match slugをmatch-date/home/awayの対応表に結合。Data Siteの`match_card_id`との直接対応は未確認 | 表示単位は%で、小数表示の有無・home+awayが常に100かは全件検査が必要 | 古いseason、表示なし試合、丸めによる合計差の可能性 | 2020〜2025のprototype候補。2015〜2019は追加検証が必要 | **B** |

## 実際に確認した公式サンプル

確認日はすべて 2026-09-20 JST。公式matchページの`Match Stats / Team Stats`に、チーム名と左右の値、`Shots on Target`および`Possession (%)`の項目があることを確認した。

- 2020: [札幌 vs 川崎F、2020-08-15](https://www.jleague.jp/en/match/j1/2020/081514/stats/)、[鳥栖 vs 神戸、2020-07-08](https://www.jleague.jp/en/match/j1/2020/070821/stats/)
- 2021: [横浜FC vs G大阪、2021-08-25](https://www.jleague.jp/en/match/j1/2021/082504/stats/)
- 2022: [京都 vs 名古屋、2022-10-08](https://www.jleague.jp/en/match/j1/2022/100808/stats/)
- 2023: [神戸 vs 福岡、2023-02-18](https://www.jleague.jp/en/match/j1/2023/021805/stats/)
- 2024: [浦和 vs 京都、2024-05-15](https://www.jleague.jp/en/match/j1/2024/051510/stats/)
- 2025: [名古屋 vs 川崎F、2025-08-23](https://www.jleague.jp/en/match/j1/2025/082304/stats/)

2024のmatch pageではMatch Statsの項目順が `Shots`、`Shots on Target`、`Possession (%)`、`Corner kicks`、`Free kicks`等として表示される。したがって、既存Data Site parserの`SH`をShots on Targetとして再利用してはならない。[2024浦和対京都](https://www.jleague.jp/en/match/j1/2024/051510/stats/)

## xGの追加確認

公式の[2024 Expected Goals club stats](https://www.jleague.jp/en/j1/stats/club/2024/expected_goals/search-list/)と[2025 Expected Goals club stats](https://www.jleague.jp/en/j1/stats/club/2025/expected_goals/search-list/)は、クラブごとのシーズン集計として表示される。これは試合終了後の個別home/away xGではない。公式ページ上で以下を確認できる根拠は得られなかった。

- PK込み/除外
- Own Goalの配分
- xG providerまたはモデル仕様
- 2015〜2023および2026/27の同一定義
- 個別match IDへ戻すための公開キー

従って、season aggregateを次試合のmatch-level rolling featureへ代用しない。

## 構造化データと自動取得性

今回確認できたmatch pageは、ブラウザが表示するHTML本文に試合基本情報とMatch Statsのラベル・値が現れる形式だった。公開された、安定したmatch-level JSON/API/XHR/GraphQL endpointは今回の調査では特定していない。認証回避や非公開APIの推測は行っていない。

J.LEAGUE.jpには「データは試合翌日〜2日後に更新」とする説明があり、速報値ではなく公式更新後の値を対象にする必要がある。[公式クラブstats](https://www.jleague.jp/en/j1/stats/club/2024/)

次のprototypeでは、HTML parserを前提に次を検証する必要がある。

1. 2020〜2025の全試合で3項目が揃うか。
2. 2020以降のmatch slugと既存Data Site `match_card_id`を日付・home/awayで一意に対応できるか。
3. 2015〜2019にも同じMatch Stats DOMと項目定義が存在するか。
4. Possessionの数値形式、丸め、home+awayの合計を全件で検査する。

## 次のprototype候補

現時点でA判定はない。したがって「A判定のstatだけ」という条件に該当するprototypeはない。

追加調査を進める場合の最小サンプル候補は、B判定のShots on TargetとPossessionについて、2020〜2025から各1件、特に次の3件である。

- 2020: [札幌 vs 川崎F](https://www.jleague.jp/en/match/j1/2020/081514/stats/)
- 2024: [浦和 vs 京都](https://www.jleague.jp/en/match/j1/2024/051510/stats/)
- 2025: [名古屋 vs 川崎F](https://www.jleague.jp/en/match/j1/2025/082304/stats/)

## 注意事項

公式match pageにはJ.LEAGUEの著作権・再利用に関する注意表示があるため、大量取得前に利用条件、robots、アクセス頻度、保存・再配布範囲を確認する必要がある。今回第三者ソースは採用していない。
