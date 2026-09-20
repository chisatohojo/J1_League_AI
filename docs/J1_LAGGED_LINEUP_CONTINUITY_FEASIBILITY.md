# J1 Lagged Lineup Continuity Feasibility

調査日: 2026-09-20

## Summary

既存のSFMS02 raw cacheのみを再利用し、2015～2024のJ1 3,208試合、6,416 team appearancesを、`match_date` → `match_id`順にteam単位で監査した。

対象match自身のStarting XIは使用せず、target matchより前の2試合のXIだけから、

`previous_two_lineup_overlap = |XI(M-1) ∩ XI(M-2)|`

を計算した。全6,416 appearancesのうち、過去2試合が存在して計算可能なのは6,356、unavailableは60だった。計算可能率は **99.06%**。

## Season coverage

| season | team appearances | continuity available | unavailable | coverage |
|---:|---:|---:|---:|---:|
| 2015 | 612 | 576 | 36 | 94.12% |
| 2016 | 612 | 606 | 6 | 99.02% |
| 2017 | 612 | 608 | 4 | 99.35% |
| 2018 | 612 | 610 | 2 | 99.67% |
| 2019 | 612 | 610 | 2 | 99.67% |
| 2020 | 612 | 610 | 2 | 99.67% |
| 2021 | 760 | 758 | 2 | 99.74% |
| 2022 | 612 | 610 | 2 | 99.67% |
| 2023 | 612 | 612 | 0 | 100.00% |
| 2024 | 760 | 756 | 4 | 99.47% |
| **total** | **6,416** | **6,356** | **60** | **99.06%** |

Unavailableは欠損値ではなく、dataset開始時点またはhistoryの最初の2 appearancesで過去2試合が存在しないケースである。0補完や平均補完は行っていない。

## Overlap distribution

全6,356件:

| overlap | count |
|---:|---:|
| 0 | 10 |
| 1 | 13 |
| 2 | 22 |
| 3 | 41 |
| 4 | 104 |
| 5 | 183 |
| 6 | 388 |
| 7 | 693 |
| 8 | 1,100 |
| 9 | 1,445 |
| 10 | 1,494 |
| 11 | 863 |

- mean: **8.6419**
- median: **9**
- p10: **6**
- p90: **11**

season別のoverlap countも再計算した。極端な0～2は全体で45件であり、大量発生ではない。7前後の例は多数あり、11の完全継続も863件あった。

## Adjacent-match identity diagnostic

同一teamの連続J1 matchについて、`XI(current) ∩ XI(previous)`も診断した。対象は6,386 adjacent pairs、mean overlapは **8.6431**だった。分布は以下の通り。

| adjacent overlap | count |
|---:|---:|
| 0 | 10 |
| 1 | 13 |
| 2 | 22 |
| 3 | 41 |
| 4 | 105 |
| 5 | 183 |
| 6 | 390 |
| 7 | 694 |
| 8 | 1,103 |
| 9 | 1,457 |
| 10 | 1,503 |
| 11 | 865 |

0～2の低overlapは少数で、raw-name崩壊が全体を支配している兆候は確認できなかった。ただし、これは「同一人物identityが正しい」ことの証明ではなく、短期の表示名一致が高いという診断に留まる。

## Raw-name safety audit

既存Starting XI監査と同じA5 section、左右の`two-column-table-box-l/r`、`td.name`を使用した。各valid lineupは11人で、今回再処理でも3,208試合・6,416 lineupsすべてが11人だった。

- lineup内duplicate player name: **0**
- lineup内duplicate shirt number: **0**（既存監査結果）
- blank player name: **0**（既存監査結果）
- replacement character `�`: **0**
- raw nameの意味上のNBSP: **0**
- player ID / profile link: **0**（既存監査結果）
- stable player identity: **なし**

HTMLの`td.name`にはインデント・改行を伴うため、表示値抽出時の外周whitespaceは全70,576 starter appearancesで観測された。これはHTML formattingであり、identity normalizationとして利用したものではない。今回の比較では、HTML cellの表示文字列を既存projectの決定的な空白処理で抽出した。NFKC、fuzzy matching、manual alias、player mappingは行っていない。

同一team内の同名collisionについては、同じraw nameが複数teamで出現する既存監査結果（509 names）があり、同一team内の同一lineup重複はなかった。従って、短期隣接比較には使えるが、同姓同名を長期に同一人物と確定する用途には使えない。

## Season boundary diagnostic

前年seasonの最終matchから翌season最初のmatchへteam historyを継続した。season boundaryを跨ぐ比較は **154** 件、mean overlapは **5.9026**。通常の隣接比較より低く、off-seasonの移籍・編成変更の影響と整合する。これは表記揺れと断定せず、実際の選手変更の可能性を含む診断値として扱う。

boundary overlap分布:

`0:4, 1:5, 2:2, 3:9, 4:12, 5:18, 6:39, 7:33, 8:19, 9:12, 10:1`

## Representative sanity samples

以下はtarget match自身のXIを使わず、直前2試合のXI setだけを比較した例である。raw XI namesはcache由来の抽出値をそのまま監査し、identity統合はしていない。

| type | team_id | previous-previous match | previous match | target match | overlap |
|---|---|---:|---:|---:|---:|
| overlap 11 | team_0018 | 16804 | 16816 | 16827 | 11 |
| overlap 11 | team_0018 | 16875 | 16888 | 16893 | 11 |
| overlap 10 | team_0018 | 16841 | 16856 | 16862 | 10 |
| overlap 7前後 | team_0018 | 16910 | 16914 | 16921 | 7 |
| extreme low | team_0018 | 18198 | 20748 | 20757 | 0 |
| extreme low | team_0015 | 17103 | 21494 | 21505 | 0 |

全件監査ではoverlap 10および7前後も多数確認できた。特定player名をstable identityとして保存する処理は行っていない。

## Leakage and timing

feature候補を作る場合、target match Mについて参照するのはM-1とM-2のStarting XIだけであり、M自身のStarting XI・score・result・substitution・cards・goals・post-match statsは使用しない。SFMS02はpost-match recordだが、Starting XIの内容は本来lineup発表後に利用可能な情報であるため、将来のモデルは「kickoff直前、lineup発表後」の利用条件として扱う必要がある。

## Feasibility judgement

判定: **B — 概ね利用可能だが一部anomaly・identity limitationあり**。

理由:

- continuity coverageは99.06%で高い。
- 11人lineup coverageは100%。
- replacement character、blank、lineup内duplicateは確認されなかった。
- overlap分布は現実的で、低overlapが大量発生していない。
- season boundaryは自然に低下するため、通常season内と分けて診断すべき。
- ただしstable player IDはなく、raw-name exact matchは短期表示一致に限定される。

将来の候補は `home_prev2_lineup_overlap` と `away_prev2_lineup_overlap` の2列に限定する。stable player identity、player rating、difference、rolling average、3/5-match windowは今回採用・実装しない。
