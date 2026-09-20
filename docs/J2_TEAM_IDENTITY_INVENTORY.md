# J2 team identity inventory

確認日: 2026-09-20

## Summary

J.League Data Site SFMS01のJ2 listing（`competition_frame_ids=2`）を2015～2024について各season 1 request、計10 request取得した。SFMS02は取得していない。

- parsed matches: 4,538
- total unique source names: 40
- exact TeamMaster resolution using `source="jleague_data_site"`: 0 / 40
- unresolved source names: 40
- missing match_card_id: 0
- duplicate match_card_id: 0

0 resolvedは、SFMS01を`lang=en`で取得したため、`Akita`, `Iwata`等の英語短縮表示と、現在の日本語/文字化けしたTeamMaster aliasがexact一致しないことが主因である。これはTeamMasterにclubが存在しないことを意味しない。名前normalize・fuzzy matching・alias追加は行っていない。

## Season inventory

| season | parsed matches | unique source clubs | missing date | missing score | missing match ID | duplicate IDs | home=away |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 2015 | 462 | 22 | 0 | 0 | 0 | 0 | 0 |
| 2016 | 462 | 22 | 0 | 0 | 0 | 0 | 0 |
| 2017 | 462 | 22 | 0 | 0 | 0 | 0 | 0 |
| 2018 | 462 | 22 | 0 | 0 | 0 | 0 | 0 |
| 2019 | 462 | 22 | 0 | 0 | 0 | 0 | 0 |
| 2020 | 462 | 22 | 0 | 0 | 0 | 0 | 0 |
| 2021 | 462 | 22 | 0 | 0 | 0 | 0 | 0 |
| 2022 | 462 | 22 | 0 | 0 | 0 | 0 | 0 |
| 2023 | 462 | 22 | 0 | 0 | 0 | 0 | 0 |
| 2024 | 380 | 20 | 0 | 0 | 0 | 0 | 0 |

合計は2015～2023の22-club double round-robin 462試合×9年 + 2024の20-club 380試合 = 4,538試合だった。これはlistingの実測値であり、2025/2026は含めていない。

## Match-row identity

SFMS01の対象は`table.table-base00.search-table`だけに限定した。各result rowは10 cellsで、headerを除くvalid rowから次を取得できた。

`season`, `tournament`, `round`, `date`, `kick-off`, `home`, `score`, `away`, `venue`, `attendance`

score cell内の同一row SFMS02 linkから `match_card_id` を抽出した。2015 sampleは `Iwata 3-1 Kitakyushu`（match_card_id `17346`）、2019 sampleは `Kagoshima 4-3 Tokushima`（`21794`）、2024 sampleは `Fujieda 0-0 Nagasaki`（`30051`）で、date/home/away/score/IDが同じrowから得られた。scoreが90分resultとして扱える通常J2 listingであり、PK・playoff winnerを混ぜていない。

Date表示は英語localeの`Sun 03/08/15`形式で、parser実装時にseasonと組み合わせて厳格に解釈する必要がある。今回のinventoryではmissing date/scoreは0だった。

## Source club names

40 unique raw names：

`Akita`, `C-Osaka`, `Chiba`, `Ehime FC`, `FC Gifu`, `FC Machida`, `FC Ryukyu`, `Fujieda`, `Fukuoka`, `Gunma`, `Iwaki`, `Iwata`, `Iwate`, `Kagoshima`, `Kanazawa`, `Kashiwa`, `Kitakyushu`, `Kofu`, `Kumamoto`, `Kyoto`, `Matsumoto`, `Mito`, `Nagasaki`, `Nagoya`, `Niigata`, `Oita`, `Okayama`, `Omiya`, `Sagamihara`, `Sanuki`, `Sapporo`, `Sendai`, `Shimizu`, `Shonan`, `Tochigi`, `Tokushima`, `Tokyo-V`, `Yamagata`, `Yamaguchi`, `Yokohama FC`

既存TeamMasterのexact source-name解決結果は0件。従って今回の条件下では、未解決をA/B/Cへ安全に確定分類できないものを含む。暫定分類は次の通り。

- A（既存clubの不足aliasに見える可能性）：Iwata, Chiba, Kashiwa, Kyoto, Nagoya, Niigata, Oita, Omiya, Sapporo, Shimizu, Shonan, Yokohama FC等。ただし公式IDで照合していないため自動確定不可。
- B（TeamMaster未登録の新規/下位category候補）：Akita, Ehime FC, FC Gifu, Fujieda, Iwaki, Iwate, Kagoshima, Kanazawa, Kitakyushu, Kumamoto, Matsumoto, Mito, Nagasaki, Okayama, Sagamihara, Sanuki, Tochigi, Tokushima, Yamagata, Yamaguchi等。ただし歴史上J1経験の有無だけで判定していない。
- C（identity不明）：C-Osaka, FC Machida, FC Ryukyu, Fukuoka, Gunma, Kofu, Sendai, Tokyo-V等の表示差を含む全名称は、exact official alias/club IDなしには確定不可。

この分類は調査優先度であり、TeamMasterへの追加根拠ではない。

## Official club identifier

今回のSFMS01 result rowで安定して確認できたidentifierはmatch-levelのSFMS02 `match_card_id`だけだった。club name自体にclub ID、team ID、slugを持つlink/query parameterは確認できなかった。従ってofficial club identifier coverageは **0件確認**。club identityは、SFMS01以外の公式team directoryや別の公式識別子を追加確認する必要がある。

## J1 ↔ J2 continuity

同じ英語表示名をそのままJ1の日本語source namespaceへ渡せないため、今回の10 listingだけではJ1↔J2をstable `team_id`で全件確認できなかった。代表的にIwata、Omiya、Sapporo、Shimizu、Kashiwa等はJ1側に対応clubが存在する可能性が高いが、これはteam name推測であり、continuityの証明には使っていない。

次の段階では、公式club directoryで得られるstable club identityまたは公式のsource-specific aliasを取得し、日付付きTeamMaster解決を行う必要がある。今回、promotion auditの対象clubについてもこのidentity mappingを勝手に追加していない。

## Extension estimate

今回のexact audit結果だけから、既存TeamMasterの不足alias数と新permanent team_id数を安全に採番することはできない。保守的な上限は、未解決source name 40件を全て独立clubと仮定した40件だが、英語表記差・短縮名・改称を含むため過大推定である。

- new permanent team_id候補：未確定（上限40、採番は未実施）
- alias追加候補：未確定（上限40、追加は未実施）

## J3 limitation

J3は今回収集していない。J3→J2で初登場するclubについては、J2初戦以前のrating stateが不明である。ただしJ2参加後はJ2 matchでratingを更新できる。この制約はJ1+J2 Elo replayへ進む際に明記する必要がある。

## Final decision

**B: 中規模だが実施可能。**

SFMS01 listingとmatch_card_idは全seasonで安定して取得でき、match collectionの基盤はある。一方、40 source namesが既存TeamMasterとexact一致せず、club identifierもrowから得られないため、identity整備なしにJ1+J2 Eloへ進むことはできない。

Network request: 10（各seasonのSFMS01 listingを1回、interval約0.3秒）。SFMS02、2025、2026は使用していない。CSV、production collector、TeamMaster、Eloは変更していない。

## Revised identity audit

前版の `0 / 40` はidentity不足の結論としては誤っていた。原因は、inventory取得を`lang=en`で行い、`Iwata`, `Chiba`, `Kyoto`等の英語短縮表示を、TeamMasterの`source="jleague_data_site"`に登録された日本語表示（現在のCSVでは一部encoding-corruptedな文字列）へ直接exact照合していたことだった。

確認内容：

- source namespaceは実際に `jleague_data_site` を使用していた。
- ただしsource localeがEnglishだった。
- Japanese SFMS01の同じresult rowでは、home/awayに公式club profile linkがあり、例として`/club/iwata/profile/`, `/club/chiba/profile/`を確認した。
- score cellには同一rowのSFMS02 `match_card_id` linkがあり、match identityとclub slugを別々のDOM領域から混ぜていない。
- raw English nameのreprにはleading/trailing whitespace、NBSP、tabはなく、通常の英語短縮文字列だった。日本語localeのraw textは表示名とprofile slugを持つ。
- `strip`, whitespace collapse, NFKCだけではEnglish nameと既存CSVのcorrupted Japanese aliasは一致しなかった。normalizationでresolutionしていない。

公式club profile slugをTeamMasterの既存`source_club_id`と比較するdiagnosticでは、24 namesが一意の既存team_idへ対応し、16 namesは既存source_club_idに対応しなかった。slug対応は既存公式識別子による候補確認であり、TeamMasterやCSVは変更していない。

### Revised 40-name table

`raw_source_name`は前回English listingからのrepr。`official_profile_slug`はJapanese SFMS01の同一home/away cellのlinkから取得した値。exact alias列はsource=`jleague_data_site`の文字列exact比較、normalization列は診断のみ。

| raw_source_name | repr diagnostics | official_profile_slug | exact jleague_data_site team_id | canonical/other exact team_id | normalization candidate | classification |
|---|---|---|---|---|---|---|
| Akita | `'Akita'`, no ws | akita | - | - | - | new_club_candidate |
| C-Osaka | `'C-Osaka'`, no ws | cosaka | - | - | - | existing_team_missing_alias |
| Chiba | `'Chiba'`, no ws | chiba | - | team_0001 | - | existing_team_missing_alias |
| Ehime FC | `'Ehime FC'`, no ws | ehime | - | - | - | new_club_candidate |
| FC Gifu | `'FC Gifu'`, no ws | gifu | - | - | - | new_club_candidate |
| FC Machida | `'FC Machida'`, no ws | machida | - | team_0014 | - | existing_team_missing_alias |
| FC Ryukyu | `'FC Ryukyu'`, no ws | ryukyu | - | - | - | new_club_candidate |
| Fujieda | `'Fujieda'`, no ws | fujieda | - | - | - | new_club_candidate |
| Fukuoka | `'Fukuoka'`, no ws | fukuoka | - | team_0004 | - | existing_team_missing_alias |
| Gunma | `'Gunma'`, no ws | kusatsu | - | - | - | new_club_candidate |
| Iwaki | `'Iwaki'`, no ws | iwaki | - | - | - | new_club_candidate |
| Iwata | `'Iwata'`, no ws | iwata | - | team_0007 | - | existing_team_missing_alias |
| Iwate | `'Iwate'`, no ws | - | - | - | - | new_club_candidate |
| Kagoshima | `'Kagoshima'`, no ws | kagoshima | - | - | - | new_club_candidate |
| Kanazawa | `'Kanazawa'`, no ws | kanazawa | - | - | - | new_club_candidate |
| Kashiwa | `'Kashiwa'`, no ws | kashiwa | - | team_0009 | - | existing_team_missing_alias |
| Kitakyushu | `'Kitakyushu'`, no ws | kitakyushu | - | - | - | new_club_candidate |
| Kofu | `'Kofu'`, no ws | kofu | - | team_0012 | - | existing_team_missing_alias |
| Kumamoto | `'Kumamoto'`, no ws | kumamoto | - | - | - | new_club_candidate |
| Kyoto | `'Kyoto'`, no ws | kyoto | - | team_0013 | - | existing_team_missing_alias |
| Matsumoto | `'Matsumoto'`, no ws | matsumoto | - | team_0015 | - | existing_team_missing_alias |
| Mito | `'Mito'`, no ws | mito | - | team_0016 | - | existing_team_missing_alias |
| Nagasaki | `'Nagasaki'`, no ws | nagasaki | - | team_0017 | - | existing_team_missing_alias |
| Nagoya | `'Nagoya'`, no ws | nagoya | - | team_0018 | - | existing_team_missing_alias |
| Niigata | `'Niigata'`, no ws | niigata | - | team_0019 | - | existing_team_missing_alias |
| Oita | `'Oita'`, no ws | oita | - | team_0020 | - | existing_team_missing_alias |
| Okayama | `'Okayama'`, no ws | okayama | - | team_0021 | - | existing_team_missing_alias |
| Omiya | `'Omiya'`, no ws | omiya | - | team_0022 | - | existing_team_missing_alias |
| Sagamihara | `'Sagamihara'`, no ws | sagamihara | - | - | - | new_club_candidate |
| Sanuki | `'Sanuki'`, no ws | sanuki | - | - | - | new_club_candidate |
| Sapporo | `'Sapporo'`, no ws | sapporo | - | team_0023 | - | existing_team_missing_alias |
| Sendai | `'Sendai'`, no ws | sendai | - | team_0024 | - | existing_team_missing_alias |
| Shimizu | `'Shimizu'`, no ws | shimizu | - | team_0025 | - | existing_team_missing_alias |
| Shonan | `'Shonan'`, no ws | shonan | - | team_0026 | - | existing_team_missing_alias |
| Tochigi | `'Tochigi'`, no ws | tochigi | - | - | - | new_club_candidate |
| Tokushima | `'Tokushima'`, no ws | tokushima | - | team_0027 | - | existing_team_missing_alias |
| Tokyo-V | `'Tokyo-V'`, no ws | tokyov | - | team_0028 | - | existing_team_missing_alias |
| Yamagata | `'Yamagata'`, no ws | yamagata | - | team_0031 | - | existing_team_missing_alias |
| Yamaguchi | `'Yamaguchi'`, no ws | yamaguchi | - | - | - | new_club_candidate |
| Yokohama FC | `'Yokohama FC'`, no ws | yokohamafc | - | team_0032 | - | existing_team_missing_alias |

### Revised counts

- unique raw source names: 40
- already_resolved_exact: 0
- existing_team_missing_alias: 24
- format_discrepancy_manual_review: 0
- new_club_candidate: 16
- ambiguous: 0
- estimated new permanent team IDs: 16 candidates, subject to a separate official identity audit
- estimated alias additions: 24 existing-club source aliases, subject to review

「canonical/other exact」はTeamMaster name exactではなく、同一公式profile slug / existing `source_club_id`から得たdiagnostic candidateである。従って、今回これらを`resolve_team_id`で自動確定したり、aliasを追加したりしていない。旧inventoryの0/40は、English localeとsource-name encoding/locale不一致をidentity未登録と取り違えた結果である。
## Japanese-locale final audit

日本語locale（`lang=ja`）で2015～2024を各1 request再取得した。home/away cellのraw nameをtrim・normalizeせずに保持し、同じcellのofficial club linkとTeamMaster exact resolutionを確認した。

| English raw | Japanese raw repr | official slug / link | existing team_id | classification |
|---|---|---|---|---|
| C-Osaka | `'�b���'` | cosaka | team_0002 | already_resolved_exact |
| Chiba | `'��t'` | chiba | team_0001 | already_resolved_exact |
| FC Machida | `'���c'` | machida | team_0014 | already_resolved_exact |
| Fukuoka | `'����'` | fukuoka | team_0004 | already_resolved_exact |
| Iwata | `'�֓c'` | iwata | team_0007 | already_resolved_exact |
| Kashiwa | `'��'` | kashiwa | team_0009 | already_resolved_exact |
| Kofu | `'�b�{'` | kofu | team_0012 | already_resolved_exact |
| Kyoto | `'���s'` | kyoto | team_0013 | already_resolved_exact |
| Matsumoto | `'���{'` | matsumoto | team_0015 | already_resolved_exact |
| Mito | `'����'` | mito | team_0016 | already_resolved_exact |
| Nagasaki | `'����'` | nagasaki | team_0017 | already_resolved_exact |
| Nagoya | `'���É�'` | nagoya | team_0018 | already_resolved_exact |
| Niigata | `'�V��'` | niigata | team_0019 | already_resolved_exact |
| Oita | `'�啪'` | oita | team_0020 | already_resolved_exact |
| Okayama | `'���R'` | okayama | team_0021 | already_resolved_exact |
| Omiya | `'��{'` | omiya | team_0022 | already_resolved_exact |
| Sapporo | `'�D�y'` | sapporo | team_0023 | already_resolved_exact |
| Sendai | `'���'` | sendai | team_0024 | already_resolved_exact |
| Shimizu | `'����'` | shimizu | team_0025 | already_resolved_exact |
| Shonan | `'�Ó�'` | shonan | team_0026 | already_resolved_exact |
| Tokushima | `'����'` | tokushima | team_0027 | already_resolved_exact |
| Tokyo-V | `'�����u'` | tokyov | team_0028 | already_resolved_exact |
| Yamagata | `'�R�`'` | yamagata | team_0031 | already_resolved_exact |
| Yokohama FC | `'���lFC'` | yokohamafc | team_0032 | already_resolved_exact |
| Akita | `'�H�c'` | akita | - | new_club_candidate_with_slug |
| Ehime FC | `'���Q'` | ehime | - | new_club_candidate_with_slug |
| FC Gifu | `'��'` | gifu | - | new_club_candidate_with_slug |
| FC Ryukyu | `'����'` | ryukyu | - | new_club_candidate_with_slug |
| Fujieda | `'���}'` | fujieda | - | new_club_candidate_with_slug |
| Gunma | `'�Q�n'` | kusatsu | - | new_club_candidate_with_slug |
| Iwaki | `'���킫'` | iwaki | - | new_club_candidate_with_slug |
| Kagoshima | `'������'` | kagoshima (nonstandard `/day/#profile`) | - | new_club_candidate_with_slug |
| Kanazawa | `'����'` | kanazawa | - | new_club_candidate_with_slug |
| Kitakyushu | `'�k��B'` | kitakyushu | - | new_club_candidate_with_slug |
| Kumamoto | `'�F�{'` | kumamoto | - | new_club_candidate_with_slug |
| Sagamihara | `'���͌�'` | sagamihara | - | new_club_candidate_with_slug |
| Sanuki | `'�]��'` | sanuki | - | new_club_candidate_with_slug |
| Tochigi | `'�Ȗ�'` | tochigi | - | new_club_candidate_with_slug |
| Yamaguchi | `'�R��'` | yamaguchi | - | new_club_candidate_with_slug |
| Iwate | `'���'` | no club profile link | - | ambiguous |

日本語raw nameとTeamMasterのexact resolveにはtrim、NFKC、whitespace collapse、fuzzy matchingを使っていない。24件はexact resolveとslug対応が同じteam_idで一致し、不一致は0件だった。

### Final counts

- Japanese exact resolved: **24**
- existing missing alias: **0**
- new club candidate with stable slug: **15**
- ambiguous: **1**（Iwate）
- estimated new permanent team IDs: **15**
- estimated alias rows needed: **0** for the 24 exact-resolved clubs

### The two previous slug gaps

- **Iwate**（English raw `Iwate`, Japanese raw `'���'`, 2022 only）：全出現rowでclub profile linkがなく、special team・withdrawal・renameとは公式根拠なしに断定できないためambiguousに残した。
- **Kagoshima**（English raw `Kagoshima`, Japanese raw `'������'`, 2019～2024）：通常の`/club/{slug}/profile/`ではなく`/club/kagoshima/day/#profile`という非標準linkだった。pathのclub slugは確認できるためnew club candidate with slugとした。

### New candidate season ranges

| candidate | first J2 season | last J2 season |
|---|---:|---:|
| Akita | 2021 | 2024 |
| Ehime FC | 2015 | 2024 |
| FC Gifu | 2015 | 2019 |
| FC Ryukyu | 2019 | 2022 |
| Fujieda | 2023 | 2024 |
| Gunma | 2015 | 2024 |
| Iwaki | 2023 | 2024 |
| Kagoshima | 2019 | 2024 |
| Kanazawa | 2015 | 2023 |
| Kitakyushu | 2015 | 2021 |
| Kumamoto | 2015 | 2024 |
| Sagamihara | 2021 | 2021 |
| Sanuki | 2015 | 2018 |
| Tochigi | 2015 | 2024 |
| Yamaguchi | 2016 | 2024 |

## Iwate final official identity audit (2026-09-20)

This audit used only official J.League / J.League Data Site pages. No
TeamMaster row, alias, or permanent team ID was added.

### Result

| Item | Official evidence |
|---|---|
| Japanese official club name | いわてグルージャ盛岡 |
| English official display name | Iwate Grulla Morioka |
| 2022 SFMS01 Japanese display | 岩手 |
| 2022 SFMS01 English display | Iwate |
| Official stable identifier | Data Site `team_ids=269` query identifier |
| Profile slug in the 2022 SFMS01 row | Not present; no profile-link slug is claimed |
| Final classification | `new_club_candidate_with_stable_official_id` |

The official Data Site team-filtered 2022 listing uses `team_ids=269` and
returns J2 rows involving 岩手, including Oita vs 岩手, 岩手 vs Niigata,
Yamagata vs 岩手, and 岩手 vs Mito. This is a direct same-source linkage
between the official team identifier and the 2022 J2 participant; it is not
an identity inferred from the English word “Iwate”.

The official Data Site 2022 J2 aggregate page also lists 岩手 with 21 home
matches. The official J.League 2022 standings identify the club as
いわてグルージャ盛岡 and place it in J2. The official 2022 J2 schedule PDF
uses the full Japanese name in fixtures. An official J.League match page
further presents the same club as いわてグルージャ盛岡 / 岩手, while the
official English match page presents Iwate Grulla Morioka / IWATE.

Sources checked on 2026-09-20:

- [Data Site 2022 team-filtered match listing](https://data.j-league.or.jp/SFMS01/search?competition_years=2022&home_away_select=0&team_ids=269)
- [Data Site 2022 J2 aggregate page](https://data.j-league.or.jp/SFTD12/search?competitionFrame=2&competitionFrameName=%EF%BC%AA%EF%BC%92%E3%83%AA%E3%83%BC%E3%82%B0&endCompetitionYear=2022&startCompetitionYear=2022&teamFlag=1)
- [Official 2022 J2 standings](https://www.jleague.jp/sp/standings/2022/j2.html)
- [Official 2022 J2 schedule PDF](https://www.jleague.jp/img/pdf/schedule_j2_2022.pdf)
- [Official Japanese 2022 match page](https://www.jleague.jp/match/j2/2022/100204/review/)
- [Official English 2022 match page](https://www.jleague.jp/en/match/j2/2022/040902/)

The locally cached SFMS01 Japanese raw value remains encoding-corrupted in
the existing audit artifact, and the English raw value is `Iwate`. No
replacement-character string was decoded by guess, normalized, fuzzy-matched,
or used as the basis for the decision. The decision rests on the official
2022 listing identifier and the independent official Japanese/English club
names above.

### Revised inventory conclusion

Iwate moves out of `ambiguous` and into the new-club candidate set. The
revised totals are:

- Japanese exact resolved: 24
- existing missing alias: 0
- new club candidates with an official stable identifier: 16
- ambiguous: 0
- estimated new permanent team IDs: 16 (allocation not performed)
- aliases added in this audit: 0

The 16 candidates require a future TeamMaster extension review; this audit
does not decide ID allocation or add aliases.
