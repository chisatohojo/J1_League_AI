# J.LEAGUE Official Match Stats Data-Path Audit

確認日: 2026-09-20 (JST)

## Scope

代表sampleは2024年5月15日 Urawa Reds–Kyoto Sanga、公式URLは
`https://www.jleague.jp/en/match/j1/2024/051510/stats/`。追加sampleは使用しなかった。2025/2026、380試合crawl、collector実装は対象外である。

## Observed page and identity

公式ページ本文では、competition=`MEIJI YASUDA J1 League`、date=`15 May 2024`、Matchweek 14、home=`Urawa Reds`、away=`Kyoto Sanga F.C.`、score=`3-0`を確認した。既存2024 J1 datasetの同日・同カードと一致する。ページは`Match Stats → Team Stats`を表示する。

## Runtime / request investigation

利用可能な実行環境にChromium/Playwright/Seleniumは存在しなかったため、DevTools/HAR相当のrequest interceptionは実行できなかった。公式ページを1回、ブラウザ実行結果として提供される本文とsource/RSCを照合した。

確認できた範囲では、最終statsを返す独立した公開JSON、GraphQL、XHR endpointのURLは特定できなかった。URLを推測してアクセスする調査は行っていない。

| 項目 | 結果 |
| --- | --- |
| sample数 | 1 |
| 実測request数 | 1 page request（内部browser subrequestの内訳は取得不能） |
| structured endpoint | 未特定 |
| authentication / cookie | 未確認。通常の公式ページ閲覧にlogin画面はない |
| response content type | `text/html` pageを確認。内部runtime responseの個別型は未取得 |
| match identifier | URL path `2024/051510` とページidentityで確認 |

## Static/RSC values versus rendered page

公式ページの`Team Stats`には、以下のラベルが存在する。

`Shots`, `Shots on Target`, `Possession (%)`, `Corner kicks`, `Free kicks`, `Offsides`, `Fouls`, `YC / RC`。

しかしsampleで取得できるHTML/RSC本文の値は、Shots on Target、Possession、Foulsを含め`0`または`0%`のinitial/placeholder状態だった。ブラウザ表示本文として確認できた値も同じで、最終match statsが別requestから供給された証拠は得られなかった。Possessionもhome+away=`0%+0%`であり、試合最終値としては成立しない。

従って、今回のsampleでは次を確認できなかった。

- Shots on Targetの非zero final value
- Possessionの最終home/away value
- Offsides/Foulsのfinal value
- 同じresponse内のpasses、pass accuracy、tackles、interceptions、blocks、distance、sprint、xG

## Data-path judgement

現時点の根拠では、最終stats供給元は特定できない。判断は **C** とする。

理由は、静的HTML/RSCにplaceholderがあり、利用可能な実browser network captureがなく、公開structured endpointも特定できなかったためである。browser-only renderingの可能性は残るが、今回のsampleだけでは「取得可能」とは判定しない。

もし今後再調査する場合は、実Chromiumのrequest interceptionまたはHAR取得環境を用い、同じsampleでrequest URL・method・response JSON・home/away fields・認証条件を記録する必要がある。endpointを推測して大量取得することはしない。

## Source

- [J.LEAGUE official Urawa Reds–Kyoto match stats](https://www.jleague.jp/en/match/j1/2024/051510/stats/)
- [J.LEAGUE official Urawa Reds–Kyoto match page](https://www.jleague.jp/en/match/j1/2024/051510/)

