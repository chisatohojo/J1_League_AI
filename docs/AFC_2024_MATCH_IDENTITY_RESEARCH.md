# AFC 2024 Match Identity Research

確認日：2026-09-20

## 結論

判定は **B** とする。

2024年開催の対象試合について、AFC公式ページ・公式fixture PDFから日付、home、away、competition、stage / matchdayは取得できる。一方、2015/2019の `stats.the-afc.com/match_report/{numeric_id}` に相当する共通のstable official match IDは、2024サンプルでは確認できなかった。

true-rest用途に限れば、official fixture fieldsから作る `derived_fixture_key` は採用候補になる。ただし公式IDではないことを明示し、source URLとPDF provenanceを併記する必要がある。collector実装は今回行っていない。

## 2023/24 AFC Champions League

2024年開催のYokohama F. Marinos関連試合を確認した。AFC公式articleには、試合日、対戦カード、competition、finalのleg情報が本文に存在する。例えば2024-05-11のfinal first legは Yokohama F. Marinos 2-1 Al Ain と記載されている。

Primary sample：

- [AFC official final first-leg article](https://www.the-afc.com/en/club/afc_champions_league/news/second_half_surge_gives_yokohama_narrow_advantage_over_al_ain.html)
- [AFC 2023/24 archive page](https://www.the-afc.com/en/more/content/afc_champions_league_2023-2024_-_archive_download.html)

確認できたもの：

- match date：可
- home / away：可
- competition：可
- stage / leg：article本文または見出しから可
- official match page ID：確認できず
- JSON-LD / embedded fixture ID：対象articleの確認範囲では、stable match identityとして利用できるものは確認できず
- 旧 `stats.the-afc.com` への公式link：対象articleからは確認できず

## 2024/25 AFC Champions League Elite

AFC公式のLeague Stage fixture PDFを確認した。PDFには、competition、matchday、日付、home、away、venue、club codeが記載されている。日本のJ1 clubについても、Kawasaki Frontale、Yokohama F. Marinos、Vissel Kobeが公式schedule上で確認できる。

Primary sample：

- [AFC official ACL Elite League Stage schedule PDF](https://assets.the-afc.com/2024-25_ACL_Elite/Draw/Group_Stage/ACL-Elite-League-Stage---Draw-Results-%26-Match-Schedule.pdf)

PDFで確認できる例：

- MD1：Gwangju FC vs Yokohama F. Marinos、Buriram United vs Vissel Kobe、Kawasaki Frontale vs Gwangju FC等
- MD2：Kawasaki Frontale vs Gwangju FC、Vissel Kobe vs Shandong Taishan、Yokohama F. Marinos vs Ulsan HD等
- MD3以降：matchday、日付、home、awayが同じ形式で記載

確認できたもの：

- match date：可
- home / away：可
- competition：可
- stage / matchday：可
- official fixture ID / event ID：確認できず
- official numeric match ID：確認できず
- public JSON/API endpoint：確認できず
- club code：可。ただしこれはfixture identityではなくdraw上のteam code

## Page source / embedded identifier investigation

2024 AFC articleのpage sourceと確認可能なscript / metadataを限定確認した。match ID、fixture ID、event ID、game ID、Opta ID、stable JSON-LD identifier、公開fixture API endpointとして再利用できる値は確認できなかった。

記事URLに含まれるslugや画像・記事内部の数値は、試合単位の公式match identityである根拠がないため採用しない。数値IDの総当たりや非公開endpointの探索も行っていない。

## stats.the-afc.com compatibility

2015/2019の旧stats deliveryは、例えば次のようにnumeric match report IDを持つ。

- [2015 AFC match report 9724](https://stats.the-afc.com/match_report/9724)
- [2019 AFC match report 16143](https://stats.the-afc.com/match_report/16143)

2024開催の2023/24 ACLについて、公式ページや既存の公式linkから旧stats match reportへ辿れる証拠は確認できなかった。したがって、旧numeric ID方式を2024へ拡張することはできない。

2024/25 ACL Eliteについては、旧statsの同一delivery構造自体が確認できず、新しいcompetition formatの公式fixture PDFが主要deliveryとなっている。

## Derived fixture key evaluation

候補schema：

```text
identity_type = "derived_fixture_key"
source_match_id = null
match_key = afc:derived:<competition>:<date>:<home>:<away>:<stage_or_matchday>
```

生成には、AFC公式sourceに明記された次の値だけを使う。

- canonical competition
- official match date
- official home name
- official away name
- official stage / matchday

評価：

1. 同一competition内の確認済みfixture sampleでは一意だった。
2. 同日同カードの重複は確認sampleにはなかった。
3. home / awayの向きは保持できる。
4. future resultや第三者情報は不要。
5. source URLとPDF URLを併記できる。
6. `identity_type` と `source_match_id=null` により公式IDとの違いをschema上明示できる。

ただし、derived keyは公式IDではない。大会全fixtureを実装前に再検証し、同一competition内の重複、日付変更、stage表記揺れを検出してrejectする必要がある。特に公式PDFがschedule版である場合、確定結果との日付差替えを別途確認する必要がある。

## Source hierarchy

1. AFC公式structured fixture/result pageまたは公式公開JSON（確認できる場合）
2. AFC公式match article（試合結果の補助根拠）
3. AFC公式fixture/result PDF
4. AFC公式archive page

2024サンプルでは、ACL Eliteは公式fixture PDFが最も再現可能な一次sourceだった。2023/24 ACLのfinal等は公式articleが補助sourceになる。現時点では、全試合共通のstructured match endpointを確認できていない。

## Final decision

**B：stable official IDは確認できないが、official fixture fieldsでderived keyが安全。**

次のprototypeでは、2024年のJ1参加試合だけを対象に、公式PDF/articleから取得した値でderived keyの全件一意性を検証する。公式IDとして扱わず、`identity_type`、`source_match_id`、`source_url`、provenanceを分離して保存する。

今回、collector、CSV、TeamMasterは変更していない。
