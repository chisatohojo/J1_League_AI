# J.LEAGUE advanced stats delivery research

調査日: 2026-09-20 JST  
対象: J.LEAGUE.jpのJ1 match stats page。xG、全試合collector、parser変更は今回行っていない。

## 結論

今回確認した2024・2025を中心とする過去match pageでは、HTML本文とReact Server Components payloadの両方に、Match Statsのラベルと数値が存在する。しかし、確認したページではShots on Targetが0、Possessionがhome=0% / away=0%であり、実試合の確定値としては不自然だった。

ブラウザ表示用の別公開endpointは今回特定できなかった。ページHTML内のRSC payloadに同じ0値が埋め込まれており、確認できた範囲では「HTMLはplaceholderだがブラウザ後処理で別endpointから実値に置き換わる」とは判断できない。

現時点の判定は以下である。

- **Shots on Target: C** — 項目と左右構造は存在するが、過去matchで実値を取得できる経路を確認できない。
- **Possession: C** — 同上。0%/0%は確定値として利用できず、historical match statsとして保存されていない可能性が高い。
- collector本実装へは進まない。

## 確認したsample

確認日はすべて2026-09-20 JST。HTTP取得は3ページとも成功した。

| Season | URL | HTML/RSCの表示 |
|---:|---|---|
| 2023 | [Kobe vs Fukuoka](https://www.jleague.jp/en/match/j1/2023/021805/stats/) | Match Statsラベルを確認。値は0系で、実値endpointは未確認 |
| 2024 | [Urawa vs Kyoto](https://www.jleague.jp/en/match/j1/2024/051510/stats/) | Shots on Target=0、Possession=0%/0% |
| 2025 | [Nagoya vs Kawasaki-F](https://www.jleague.jp/en/match/j1/2025/082304/stats/) | Shots on Target=0、Possession=0%/0% |

2024ページのRSC payloadには、次の構造が含まれている。

- `Shots-info-home` / `Shots-info-away`
- `Shots on Target-info-home` / `Shots on Target-info-away`
- `Possession-info-home` / `Possession-info-away`
- `o-team-comparison__club-name`によるhome/away team名

したがって、ラベルとhome/awayのDOM/RSC構造自体は取得可能である。一方、対応する値は確認sampleでは0だった。

## 0値の原因調査

### HTML/RSC

ページsourceにはNext.jsのscriptとRSC payloadが埋め込まれている。RSC payload内にMatch Statsの構造と値があり、単なる画面描画後だけに生成されるラベルではない。確認した代表ページでは、ブラウザ表示用に送られるpayload自体が0値を保持していた。

### JavaScript / endpoint追跡

2024 match pageが参照するNext.js script一覧を確認し、26 scriptを対象に`api/`、`fetch`、`graphql`、`matchStats`、`match_stats`、`ball_rate`、`shoot_on_target`等を検索した。

確認できたものはNext.js内部処理、一般的なpreview API、翻訳や画像関連処理であり、Match Statsの実値を返す公開endpointは特定できなかった。

確認できなかったもの：

- match stats専用の公開JSON endpoint
- match identifierを受け取るstats API
- Shots on Target fieldを返すAPI
- Possession fieldを返すAPI
- GraphQL endpoint
- 認証不要で再現可能なXHR/fetch endpoint

非公開token抽出、認証回避、アクセス制御回避は行っていない。

### ブラウザ後処理とlive-only仮説

今回の静的source調査だけでは、live match中だけ別データが入る可能性を完全には排除できない。しかし、過去matchページのserver payloadが0値であり、ページsourceからhistorical用endpointも確認できなかったため、現時点では次の順に近い。

1. **Bに近い:** 過去matchでは実値がページpayloadに保存されていない可能性が高い。
2. **Cの可能性:** 実値がlive match配信・一時データに限定され、終了後に保持されない可能性がある。
3. **Aではない:** ブラウザ上で0以外の過去match値が表示され、それを再現できることは確認できていない。

従って、今回のsampleからは「HTMLのplaceholderをブラウザ後処理で実値へ置換している」とは言えない。ブラウザ表示も確認範囲では0系で、historical statsとして保存されていないという仮説を支持する。

## match ID

J.LEAGUE.jp URLは`/en/match/j1/YYYY/MMDDNN/stats/`形式で、Data Siteの`match_card_id`と同一であることは確認していない。将来実値endpointが見つかった場合も、既存match_idへ直接代入せず、次の対応表を介すべきである。

`J.LEAGUE.jp match slug + match_date + home_team_id + away_team_id`  
→ `TeamMaster`でhome/awayを解決  
→ 既存Data Site match_id

文字列normalizeやfuzzy matchingは使用しない。

## 次に取るべき行動

collector実装は保留する。次に進む場合は、公式サイトの利用条件に従ったブラウザ開発者ツールで、実際のlive matchページを1件だけ監視し、公開XHR/fetchの有無を確認する。その際も、認証回避や非公開token利用は行わない。

live中にのみ実値が存在し、Full Time後に0へ戻るなら、historical pre-match rolling featureには不適である。過去matchのFull Time値が公式に再提供されない限り、第三者ソースを別途調査する必要がある。

