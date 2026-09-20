# SofaScore J1 API / Data Path Audit

調査日: 2026-09-20

## 結論

判定: **C — 公式Public APIとして安全に利用できる経路を確認できず、historical ratingの大量取得は見送る。**

SofaScoreの公式FAQは、data providerとの契約上、提供データをAPI endpointの形で共有できないと説明している。[SofaScore公式FAQ](https://sofascore.helpscoutdocs.com/article/129-sports-data-api-availability)

SofaScore web pageにはmatch detail、Lineups導線、rating概念、player profile URLは存在する。しかし、今回の3 sampleでは、公式に文書化されたPublic APIとして、starting XI全員の`player.id`、starter flag、rating、minutesを取得できる実データ経路を確認できなかった。`api.sofascore.com/api/v1/...` のような内部・未文書化経路をcollectorの前提にしてはいけない。

## Sample結果

| season | match page | event identifier候補 | event basic | lineup導線 | starting XI IDs | rating | minutes |
|---|---|---|---|---|---|---|---|
| 2015 | [Montedio Yamagata–Sanfrecce](https://www.sofascore.com/football/match/montedio-yamagata-sanfrecce-hiroshima/KmbscNi) | `KmbscNi`（URL token） | Yes | Yes | No確認 | No確認 | No確認 |
| 2019 | [Kawasaki–Matsumoto](https://www.sofascore.com/football/match/matsumoto-yamaga-fc-kawasaki-frontale/Cccslvk) | `Cccslvk`（URL token） | Yes | Yes | No確認 | No確認 | No確認 |
| 2024 | [Sagan Tosu–Sanfrecce](https://www.sofascore.com/football/match/sagan-tosu-sanfrecce-hiroshima/KmbseNi) | `KmbseNi`（URL token） | Yes | Yes | No確認 | No確認 | No確認 |

各ページの公開本文では、日付、home/away、score、competition、Lineupsリンクを確認できた。2015 sampleは2015-09-12 1–3、2019 sampleは2019-08-04 0–0、2024 sampleは2024-07-21 1–4である。[2015 page](https://www.sofascore.com/football/match/montedio-yamagata-sanfrecce-hiroshima/KmbscNi)、[2019 page](https://www.sofascore.com/football/match/matsumoto-yamaga-fc-kawasaki-frontale/Cccslvk)、[2024 page](https://www.sofascore.com/football/match/sagan-tosu-sanfrecce-hiroshima/KmbseNi)

URL末尾のtokenはmatch pageを一意に指す候補だが、今回の公式資料では「stable event ID」としての仕様保証や、API requestで共通利用されるnumeric event IDとの対応までは確認できなかった。従って、`KmbscNi`等を公式stable IDと断定しない。

## Data path調査

### 公式Public API

公式FAQの結論は、SofaScoreがdata providerとの契約により、data sourceをAPI endpointsとして共有できないというものだった。これは、認証不要の公式Public API documentation、API key、historical lineup/rating availability、rate limitを公式に保証する資料が今回確認できなかったことを意味する。[公式API availability FAQ](https://sofascore.helpscoutdocs.com/article/129-sports-data-api-availability)

確認結果:

| 項目 | 結果 |
|---|---|
| 公式API documentation URL | 公式Public API documentationは確認できず。公式FAQのみ確認 |
| authentication | match pageは不要。APIは公式条件不明 |
| API key | unknown |
| free / paid | 公式API packageとしてはunknown |
| historical data | match pageの存在は確認。API historical lineup/ratingは未確認 |
| football lineups | match pageにLineups導線あり。API提供保証なし |
| player ratings | rating概念はmatch pageに記載。API fieldの提供保証なし |
| rate limit | 公式API条件としてunknown |
| commercial / personal use | 公式FAQはdata-provider契約上の制約を示す。大量自動取得の許諾とは解釈しない |

検索結果やcommunity-maintained documentationに内部endpointの説明が存在しても、SofaScore公式Public API documentationではないため、今回の成果物ではproduction data pathとして採用しない。

### HTML / embedded data fallback

3つのmatch pageでは、公開本文に基本match情報とLineupsリンクはあるが、starting XI全員のplayer ID、rating、minutesの一覧は確認できなかった。従って現時点でのfallbackは、ブラウザ実行またはmatchごとのpage/data取得を必要とする可能性が高い。

この方式は2015～2024の3,208試合に拡張すると大量取得になる。robots、Terms、アクセス制限を明確に確認できない状態で実行してはいけない。

## Stable player ID

SofaScoreのplayer profile URLには数値ID形式が存在する例を確認できる。[Kensuke Nagai profile](https://www.sofascore.com/football/player/kensuke-nagai/109626)

ただし、今回の3 match pageの公開本文から、starting XIの各playerへその数値IDが対応付けられたデータは取得できなかった。従って、stable player IDの存在可能性はあるが、sample lineupでのcoverageは未確認である。player nameだけでlongitudinal identityを作成してはいけない。

## Historical sample availability

| season | event data | lineup data path | starting XI IDs | rating | minutes | 判断 |
|---|---|---|---|---|---|---|
| 2015 | Yes, page | Lineups linkのみ | No | No | No | structured path未確定 |
| 2019 | Yes, page | Lineups linkのみ | No | No | No | structured path未確定 |
| 2024 | Yes, page | Lineups linkのみ | No | No | No | structured path未確定 |

ここでNoは、値が絶対に存在しないという意味ではなく、今回確認できた公式公開data pathから再現可能な形で取得できなかったという意味である。rating/minutesのhistorical coverageは未確定のまま残る。

## Methodology

SofaScore match pageは、playerに多数のdata factorに基づくratingを付与するrating systemを説明している。しかし、次は公式資料から確認できなかった。

- rating scaleの正式仕様
- proprietary modelの詳細
- 2015・2019・2024でのmethodology一貫性
- historical backfill / retroactive recalculation
- substitute・途中出場者のminutes/rating欠損規則

従って、年代をまたいだrating比較を前提にしない。

## Downstream / leakage

仮に許諾済みstructured dataが確保できた場合でも、current matchのpost-match ratingやevent statisticsを、そのmatchのpredictionへ使用してはいけない。利用できるのは、過去matchのratingをlagした履歴だけである。

将来の候補は、過去matchのstarting XI平均rating、player appearance-weighted rating、squad availability、lineup continuityなど。ただし、今回これらは実装しない。

## Final judgement

**C: 現時点では採用困難。**

SofaScoreにはhistorical match pageとLineups導線があり、URL tokenとplayer profile ID形式も確認できる。一方、公式FAQがPublic API endpoint共有を否定しており、3 sampleすべてでstarting XI player ID・rating・minutesを取得できる公式structured pathを確定できなかった。したがって、現状で可能なのはmanual/page-level確認に近く、2015～2024全件を安全に自動収集する根拠が不足している。

将来再検討する場合は、まずSofaScoreまたは正規データ提供元から、historical lineup/ratingの利用許諾とstructured feedを明示的に取得することが前提となる。

