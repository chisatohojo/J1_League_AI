# SofaScore J1 Player Rating Feasibility Audit

調査日: 2026-09-20

## 結論

判定: **B — 一部sampleは確認できるが、追加調査が必要**。

SofaScoreはJ1のhistorical competition pageとmatch pageを保持しており、少なくとも2015・2019・2024の代表matchについて、日付、home/away、score、competition、event URL、Lineups導線を確認できる。match URLはopaqueなevent identifierを含み、match-level identityには利用できそうである。

一方、今回の限定的な公開ページ確認では、starting XI全11名のstable player ID、numeric rating、minutesを3 seasonの複数matchで安定取得できることまでは確認できなかった。したがって、現段階でcollectorや大量crawlへ進めない。

## Sample確認

| season | checked sample | lineup導線 | stable event identity | player rating / minutes |
|---|---|---|---|---|
| 2015 | Montedio Yamagata vs Sanfrecce Hiroshima, 2015-09-12 | `Lineups` 表示 | URL末尾に `KmbscNi` | 全11名の数値ratingは今回未確認 |
| 2019 | Kawasaki Frontale vs Matsumoto Yamaga, 2019-08-04 | `Lineups` 表示 | URL末尾に `Cccslvk` | 全11名の数値ratingは今回未確認 |
| 2024 | Sagan Tosu vs Sanfrecce Hiroshima, 2024-07-21 | `Lineups` 表示 | URL末尾に `KmbseNi` | 全11名の数値ratingは今回未確認 |
| 2024 | Jubilo Iwata vs Kashima Antlers, 2024-08-11 | `Lineups` 表示 | URL末尾に `HmbsJmb` | 全11名の数値ratingは今回未確認 |
| 2024 | Nagoya Grampus vs Sagan Tosu, 2024-11-30 | `Lineups` 表示 | URL末尾に `LmbseNi` | 全11名の数値ratingは今回未確認 |

代表URL: [2015 sample](https://www.sofascore.com/football/match/montedio-yamagata-sanfrecce-hiroshima/KmbscNi)、[2019 sample](https://www.sofascore.com/football/match/matsumoto-yamaga-fc-kawasaki-frontale/Cccslvk)、[2024 sample](https://www.sofascore.com/football/match/sagan-tosu-sanfrecce-hiroshima/KmbseNi)。各ページは日付、score、competition、match detail、Lineupsを示す。[SofaScore J1 competition page](https://www.sofascore.com/football/tournament/japan/j1-league/196) にはseason selectorもある。

ここで「Lineups導線がある」ことと、「starting XI全員のratingが取得できる」ことは分離した。今回の公開検索・静的ページ結果では、rating値やplayer.id一覧を再現可能な形で確認できなかったため、coverageを数値化していない。

## Identity

### Match identity

match URLの末尾に、例えば `KmbscNi`、`Cccslvk`、`KmbseNi` のようなevent identifierが含まれる。これは同一match pageへのstable URL identity候補であり、既存J1 datasetとの結合では保存すべきである。ただし、それが公開仕様上の永続IDか、URL slugの一部かは今回の資料だけでは確認できない。

日付 + home/awayは補助的な照合keyとして使えるが、これだけで自動確定せず、event URL/identifierを優先する。

### Player identity

SofaScoreのplayer profileにはplayer URLと数値ID形式のURLがある例が検索結果で確認できる。[Kensuke Nagai profile](https://www.sofascore.com/football/player/kensuke-nagai/109626)

ただし、今回確認したJ1 historical match pageの静的本文では、starting XI各行にplayer IDを列挙した構造化データまでは取得できなかった。したがって、player profile linkがlineup payloadに含まれるか、公開event lineup endpointが返す `player.id` をsampleごとに検証する必要がある。名前だけでidentityを確定してはいけない。

## Rating / lineup fields

| field | feasibility at this stage | comment |
|---|---|---|
| starting XI | B | historical match pageにLineups導線はあるが、3年全体のcoverage未検証 |
| substitute list | B | match pageのlineup dataで取得できる可能性はあるが、今回payload確認なし |
| player stable ID | B | player profile URL/ID形式は確認できるが、lineup全員へのmapping未確認 |
| player rating | B | SofaScoreがmatch pageでplayer ratingを扱うことは示唆されるが、今回sampleの数値列を取得できず |
| played minutes | B | lineup/event dataで取得可能性はあるが、今回sampleで未確認 |
| missing-rating flag | B | 実payloadでrating null/欠損規則を確認する必要あり |

SofaScoreのmatch pageは「best-rated player」を表示し、rating systemが各playerにratingを付与すると説明している。しかし、これはrating概念の存在を示すだけで、2015～2024の全starting XI rating coverageを保証しない。[2019 match page](https://www.sofascore.com/football/match/matsumoto-yamaga-fc-kawasaki-frontale/Cccslvk)

## Historical coverage

今回のchecked matchesは2015が1、2019が1、2024が3。従って以下は未確定である。

- season全matchのlineup availability
- season全matchのstarting XI 11名率
- player rating available match数
- rating missing player数
- substitute rating coverage
- 2015→2019→2024で同じpayload構造が継続しているか

特に2015は検索結果上でLineupsが表示されても、現在の公開表示・payloadが当時の全starting XI/ratingを保持しているとは限らない。historical backfillの有無を追加検証する必要がある。

## Access / terms / automation

- 公開HTML: competition pageとmatch pageは閲覧可能。
- structured data: 今回、公開ページ本文から全lineupを取得できる公式documented JSON endpointは確認できなかった。
- API-like endpoint: SofaScoreに `api.sofascore.com` の公開URLは存在するが、今回の調査ではJ1 historical lineup/rating用endpointを確定しなかった。
- login / paid: 公開match page閲覧にloginは不要。ただし自動取得の許可、rate limit、API利用条件は今回確認できていない。
- robots / terms: 大量scrapingを許可する明確な記載は確認していない。robots.txt、利用規約、API条件を確認せずにcrawlしてはいけない。
- request load: 2015～2024全3,208試合をmatch page + lineup payloadで取得する方式はheavyになる可能性が高い。まず数試合の公開payloadとアクセス条件を確定すべきである。

## Methodology

SofaScoreはplayer ratingを多数のデータ要素に基づく独自rating systemとして説明している。[SofaScore match description](https://www.sofascore.com/football/match/matsumoto-yamaga-fc-kawasaki-frontale/Cccslvk)

今回確認できた範囲では、以下はunknownである。

- rating scaleの正式仕様
- proprietary modelの詳細
- season間のmethodology変更
- historical backfill / retroactive recalculation
- substitute・途中出場者のrating計算規則
- played minutesの定義と欠損規則

従って、2015・2019・2024のratingを同一尺度として直ちに比較しない。

## Existing J.League Starting XIとのlink

将来的には、既存SFMS02のraw player nameとSofaScore player IDの対応表を作れる可能性がある。しかし、safe mappingには次が必要である。

1. 同一matchのhome/awayと日付をevent IDで固定。
2. SofaScore lineupの各player ID、starting/substitute区分、minutes、ratingを取得。
3. SFMS02側のstarting XIとteam/dateを照合。
4. raw nameだけでなく、公式player profile IDを主identityとする。
5. 一致しない行、欠損rating、duplicate player IDは保留し、自動fuzzy mergeしない。

## Feature and leakage limitation

将来候補として、過去matchのstarting XI平均rating、recent appearances weighted rating、squad availability、lineup continuityなどは考えられる。

ただしratingはpost-match評価であるため、current matchのratingやcurrent event statisticsをそのmatchのpredictionへ使用してはいけない。必ず過去matchだけを時系列lagして使用する。lineup発表前に使うfeatureにするなら、実際のstarting XIではなく別のpre-match availability情報が必要になる。

## Final judgement

**B: 追加調査が必要。**

SofaScoreは、historical J1 match page、event URL identity、Lineups導線、player rating概念を提供しているため候補としては有望である。しかし、今回の少数sampleでは、starting XI 11名のplayer ID・rating・minutesを2015/2019/2024で実際に取得し、coverageと同一構造を確認するところまで到達していない。

次の調査では、利用規約とrobots/API条件を確認した上で、各年3試合程度の公開lineup payloadを取得し、`event_id / player.id / starter / minutes / rating` の実フィールドと欠損規則を検証する。そこで初めて小規模collector prototypeの可否を判断する。

