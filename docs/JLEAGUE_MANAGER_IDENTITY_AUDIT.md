# J.League manager identity audit

調査対象：`data/processed/jleague_match_managers/2015_2024_match_managers.csv`

調査日：2026-09-20

2025・2026のデータは読み込まず、network accessも行っていない。名前の自動統合、fuzzy matching、alias追加は行っていない。

## 1. Summary

3,208試合をteamごとに`match_date → match_id`順で走査し、前回J1 matchとmanager nameがexactに異なる箇所を抽出した。exact transitionは269件だった。

重要な制約として、既存cache由来のmanager nameには文字コードの置換文字（`�`）が含まれている。したがって、今回の「表記差だけに見える」判定は、意味的な同一人物判定ではなく、限定的な文字列診断に留める。表示名を復元・統合する処理は行っていない。

## 2. Exact transition count

| 項目 | 件数 |
|---|---:|
| Exact manager transitions | 269 |
| In-season | 182 |
| Season-boundary | 87 |
| Manager missing | 0 |
| manager staff IDあり | 0 |

各transitionには、team_id、前回/current match_id、両日付、両manager nameを保持して診断した。staff IDが全件nullのため、identity比較は公式表示名のexact比較のみである。

## 3. Gap distribution

`days_between_matches = current_match_date - previous_match_date` とし、指定区間で分類した。

| Gap | 件数 |
|---|---:|
| 0–14日 | 82 |
| 15–60日 | 98 |
| 61–150日 | 70 |
| 151日以上 | 19 |

Season boundaryは87件、同seasonは182件だった。

## 4. Suspicious spelling-variant candidates

空白・中黒・句読点・全半角差・大文字小文字を診断するため、調査用にのみUnicode NFKCと限定的な空白／記号除去を適用し、exact transitionの両名が一致する候補を抽出した。これはmergeではなく候補抽出であり、出力データは変更していない。

この診断で19件が候補になった。ただし、cacheの置換文字が比較結果に影響しており、19件を同一人物の表記揺れと断定できない。例として、team_0018、team_0029、team_0033で複数のmanager名が短期間に切り替わる候補があるが、原文の正しい日本語表記を復元しない限りsemantic判定はできない。

今回確認できたことは「deterministic normalizationで同じ文字列になる候補が19件ある」までであり、候補を統合することではない。

## 5. A→B→A / one-match manager cases

3試合以内にA→B→Aとなるケースは26件だった。これは、中央の1試合だけ別manager名になり、次の試合で元へ戻るone-match manager pattern 26件と同数だった。

代表例：

| team_id | previous | middle | current | manager sequence |
|---|---:|---:|---:|---|
| team_0033 | 20881 | 20893 | 20921 | A→B→A |
| team_0030 | 20935 | 20964 | 20981 | A→B→A |
| team_0029 | 19368 | 20745 | 20779 | A→B→A |
| team_0011 | 28455 | 30442 | 30462 | A→B→A |
| team_0026 | 27574 | 27592 | 27618 | A→B→A |

これらは代行監督、一時的な登録表記、実際の交代のいずれも排除できない。誤りとは断定しない。

## 6. Teams with most transitions

| team_id | exact transition count |
|---|---:|
| team_0030 | 23 |
| team_0008 | 22 |
| team_0011 | 21 |
| team_0025 | 20 |
| team_0029 | 18 |
| team_0006 | 17 |
| team_0009 | 16 |
| team_0018 | 14 |
| team_0003 | 14 |
| team_0005 | 12 |

同一team・同一seasonでtransitionが多いteamは、実際の監督交代、代行、または表示名品質の影響を含み得る。今回の集計だけでは原因を分離していない。

## 7. Manager-name frequency observations

名前ごとのappearances、represented teams、first date、last dateを集計した。上位appearanceの名前が複数teamにまたがる一方、manager名には置換文字があるため、現時点の文字列頻度を人物頻度として解釈しない。

同一teamで似た名前が並存する候補は19 transition候補の中に含まれる。特に、監督が短期間で戻るA→B→Aと、同じ人物の空白・中黒・全半角差が混在する可能性があるため、exact nameだけでmanager tenureを作ると偽transitionを含む可能性がある。

## 8. Identity limitations

1. SFMS02 cacheのmanager欄からstaff_idを取得できず、stable official IDがない。
2. cacheの一部manager nameに文字コード置換文字があり、名前の意味的比較を安全に再現できない。
3. 監督名だけでは、同一人物の表記差、代行、登録表記変更を区別できない。
4. teamを跨いだ同一人物判定は行っていない。
5. transition候補は監督交代の確定記録ではない。
6. manager featureを作るには、元HTMLのencoding品質確認またはSFIX07等のstaff IDとの別途mappingが必要である。

## 9. Recommendation for feature construction

推奨：**D. stable staff ID等を別sourceから取得しないと危険**

理由は、exact transitionが269件あり、normalization診断でも19件の候補があるうえ、staff IDが0%で、cache名に文字コード問題もあるためである。まず別sourceまたは正しいencodingの公式データからstable staff IDと在任履歴を検証し、代行監督の扱いを定義するべきである。

stable IDが取得できない間は、manager_changed等のfeatureを生成しない。少なくとも、manual manager masterと検証済みaliasを用意し、同一team内の履歴を人手確認した後に初めてfeature化する。

## 10. Reproducibility scope

- 入力：既存の2015–2024 manager CSVのみ
- 出力：Markdownのみ
- exact比較：manager nameの文字列比較
- 候補診断：限定的なNFKC／空白・記号除去のみ。統合なし
- 対象外：2025、2026、network、feature生成、model評価
