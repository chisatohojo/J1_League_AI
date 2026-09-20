# J.League Starting XI audit

確認日: 2026-09-20

## Summary

既存のSFMS02 raw cache 3,588件をネットワークなしで確認した。2015～2024のJ1 3,208試合について、全6,416 team lineupsが取得でき、全lineupが11人だった。

一方、Starting XIのplayer rowには公式player ID、profile link、player database identifierは確認できなかった。したがって、現状はraw表示名とshirt numberしか利用できず、2015～2024を安全なstable player identityで結ぶことはできない。

判定は **C**。Starting XI featureの実装は、player IDを取得できる別の公式sourceまたは厳格なplayer masterが得られるまで見送る。

## DOM structure

SFMS02の試合ページには、A5（cached HTML commentのsection marker）内に、左右の
`two-column-table-box-l` / `two-column-table-box-r` がある。各sideに `h4` のStarting XI見出しと、`two-column-table-base` のtableがあり、rowは次の4列だった。

`td.position`, `td.number`, `td.name`, `td.time`

2015、2019、2024の各2～3件相当を代表するcache（例: `16803`, `21623`, `30619`）で同じ構造を確認した。Starting XIはA5、substituteはA6、substitution eventはA7、managerはA10であり、bench・manager・scorer/card tableとは別領域である。

player nameのセル内に `a` linkはなく、player profile linkもなかった。shirt numberは表示されるが、同じ番号がチーム内で時期をまたいで再利用されるためstable identityではない。

## Coverage

| season | matches | team lineups | exactly 11 | non-11 | missing identity | duplicate player | replacement-character appearances |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 2015 | 306 | 612 | 612 | 0 | 0 | 0 | 0 |
| 2016 | 306 | 612 | 612 | 0 | 0 | 0 | 0 |
| 2017 | 306 | 612 | 612 | 0 | 0 | 0 | 0 |
| 2018 | 306 | 612 | 612 | 0 | 0 | 0 | 0 |
| 2019 | 306 | 612 | 612 | 0 | 0 | 0 | 0 |
| 2020 | 306 | 612 | 612 | 0 | 0 | 0 | 0 |
| 2021 | 380 | 760 | 760 | 0 | 0 | 0 | 0 |
| 2022 | 306 | 612 | 612 | 0 | 0 | 0 | 0 |
| 2023 | 306 | 612 | 612 | 0 | 0 | 0 | 0 |
| 2024 | 380 | 760 | 760 | 0 | 0 | 0 | 0 |
| **total** | **3,208** | **6,416** | **6,416** | **0** | **0** | **0** | **0** |

Starter appearancesは `3,208 × 2 × 11 = 70,576`。unique raw player namesは1,462だった。raw HTMLを現在のcache decode方式で調べた範囲ではreplacement character `�` は0件、blank nameも0件だった。ただし、これはstable identityがあることを意味しない。

## Identity audit

- official player ID / profile link: 0
- player IDあり: 0 / 70,576
- player IDなし: 70,576 / 70,576
- unique raw names: 1,462
- duplicate player within one lineup: 0
- duplicate shirt number within one lineup: 0
- raw nameが複数teamで現れるもの: 509

同じraw nameが複数teamで現れることは、同姓同名・表示名の再利用・cache decode上の表記問題を区別できない。名前の近さ、shirt number、team、seasonだけで人物を自動統合してはいけない。fuzzy matchingやalias自動生成は行っていない。

## Representative cached samples

以下はraw cacheから抽出した表示値。日本語の一部はcache内のraw/decode状態をそのまま示しており、読みやすくするための推測的な名前復元はしていない。

| match_id | representative season | side | shirt numbers | player link |
|---:|---:|---|---|---|
| 16803 | 2015 | home / away | home 21,25,2,3,5,31,17,10,8,7,20; away 1,6,17,3,13,5,15,22,30,11,10 | none |
| 21623 | 2019 | home / away | home 25,3,20,2,7,27,8,19,9,18,48; away 18,13,36,3,41,4,6,2,25,19,44 | none |
| 30619 | 2024 | home / away | home 1,2,50,6,33,88,14,4,99,16,7; away 1,27,15,5,39,6,8,20,11,10,23 | none |

各sampleはhome/awayとも11人で、A5のstarter tableから抽出できた。bench（A6）、substitution（A7）、manager（A10）の行はStarting XI集計に含めていない。

## Continuity feasibility

match date + match_id順でteamの前回J1 matchを追跡すること自体は可能で、season boundaryも同じteam historyを継続できる。しかし、現在取得できるidentityがraw nameのみであるため、次の計算を安全な人物単位で保証できない。

`returners = current XI ∩ previous XI`

`changes = 11 - returners`

exact raw string intersectionは暫定的な表示一致にすぎず、同一人物の表記変更を落とし、別人の同名を結合する可能性がある。したがって将来featureとして採用するには、stable player IDまたは公式player masterが必要である。

## Timing and leakage limitation

SFMS02はpost-match official recordであるが、Starting XIの内容は本来kickoff前のlineup発表後に利用可能な情報である。将来この情報を使う場合は、試合開始前（lineup発表後）のmodelとして扱う必要がある。score、result、substitution、cards、goals、post-match statsはplayer identity判断に使用していない。

## Final judgment

**C: identity不足のため見送り。**

coverageと11人構造は良好だが、stable official player identityが0件である。次に進む条件は、公式player IDを提供するsourceの確認、または検証済みplayer masterの確立である。それまではraw nameをstable identityとしてStarting XI returners/changes featureへ使用しない。

調査対象: `data/raw/jleague_match_stats/*.html` の既存cacheのみ。2025・2026およびネットワークは使用していない。
