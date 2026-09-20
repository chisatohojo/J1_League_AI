# AFC club competition delivery matrix: 2015–2024

確認日：2026-09-20

対象は各calendar yearに開催された、J1 clubが参加したAFC公式club competition。非club competitionと2025年開催matchは除外した。J1 membershipの判定対象は既存の `data/processed/jleague/{year}_matches_probe.csv` とする。

## Year-by-year matrix

| Year | Competition / J1 participants confirmed | Official listing source | Listing type | Match detail source | Identity | Official ID | Date / H-A / stage | Coverage |
|---|---|---|---|---|---|---|---|---|
| 2015 | AFC Champions League / Gamba Osaka, Kashiwa Reysol, Kashima Antlers, Urawa Red Diamonds | AFC stats tournament/match reports, AFC official guide | A | `stats.the-afc.com/match_report/{id}` | official_match_id | Yes | Yes / Yes / Yes | A |
| 2016 | AFC Champions League / Sanfrecce Hiroshima, Gamba Osaka, Urawa Red Diamonds, FC Tokyo | AFC official archive/news and legacy stats reports | A | legacy stats match report | official_match_id | Yes for linked samples | Yes / Yes / Yes | B |
| 2017 | AFC Champions League / Kashima Antlers, Urawa Red Diamonds, Kawasaki Frontale, Gamba Osaka | AFC archive plus linked legacy reports | A | legacy stats match report | official_match_id | Yes for linked samples | Yes / Yes / Yes | B |
| 2018 | AFC Champions League / Kashima Antlers, Kashiwa Reysol, Kawasaki Frontale, Cerezo Osaka | AFC archive, official technical report and linked reports | E | legacy stats report / AFC article | mixed; official ID where linked | Partial | Yes / Yes / Yes | B |
| 2019 | AFC Champions League / Kashima Antlers, Urawa Red Diamonds, Kawasaki Frontale, Sanfrecce Hiroshima | AFC official guide/archive and legacy stats reports | A | legacy stats match report | official_match_id | Yes | Yes / Yes / Yes | A |
| 2020 | AFC Champions League / Vissel Kobe, FC Tokyo, Yokohama F. Marinos | AFC archive and technical report; legacy report sample | A/E | legacy stats report and official technical report | official_match_id for linked reports | Yes for linked reports | Yes / Yes / Yes | B |
| 2021 | AFC Champions League / Kawasaki Frontale, Gamba Osaka, Nagoya Grampus, Cerezo Osaka | AFC archive, technical report and legacy reports | A/E | legacy stats match report | official_match_id for linked reports | Yes for linked samples | Yes / Yes / Yes | B |
| 2022 | AFC Champions League / Kawasaki Frontale, Urawa Red Diamonds, Yokohama F. Marinos, Vissel Kobe (sample-confirmed) | AFC official archive/news and technical report | E | AFC official article / technical report | not consistently confirmed | Partial | Yes / Yes / stage generally yes | C |
| 2023 | AFC Champions League 2022 matches held in 2023 and ACL 2023/24 / Urawa Red Diamonds, Kawasaki Frontale, Yokohama F. Marinos, Vissel Kobe | AFC archive plus official fixture PDFs/articles | D/E | official fixture PDF and article; legacy only where directly linked | mixed / derived required for modern source | Partial | Yes / Yes / Yes | B |
| 2024 | ACL 2023/24 and ACL Elite 2024/25 / Yokohama F. Marinos, Kawasaki Frontale, Vissel Kobe | AFC official archive, fixture PDFs and articles | D/E | fixture PDF and official article | derived_fixture_key | No stable common ID confirmed | Yes / Yes / Yes | B |

The 2022 participant cell intentionally records only clubs confirmed during the limited source review; it is not a claim that the row is a complete participant master. Full participant enumeration requires a dedicated official fixture extraction pass.

## Confirmed source examples

Legacy reports demonstrate the old delivery format:

- [2015 Gamba Osaka match report](https://stats.the-afc.com/match_report/9724)
- [2016 AFC match report sample](https://stats.the-afc.com/match_report/9938)
- [2017 Kashima Antlers match report](https://stats.the-afc.com/match_report/10807)
- [2017 Kawasaki Frontale match report](https://stats.the-afc.com/match_report/10872)
- [2018 Kashima Antlers final report](https://stats.the-afc.com/match_report/13401)
- [2019 Kashima Antlers match report](https://stats.the-afc.com/match_report/16143)
- [2020 Vissel Kobe match report](https://stats.the-afc.com/match_report/18367)
- [2021 Gamba Osaka match report](https://stats.the-afc.com/match_report/20717)

The old report contains competition, stage, date, home, away and a numeric report ID. It may be used only when an official listing or official link supplies the report URL. Numeric ID enumeration is prohibited.

For modern delivery:

- [AFC 2017 archive](https://www.the-afc.com/en/club/afc_champions_league/archive/2017.html)
- [AFC 2018 archive](https://www.the-afc.com/en/club/afc_champions_league/archive/2018.html)
- [AFC 2020 archive](https://www.the-afc.com/en/more/content/afc_champions_league_2020_archive_home.html)
- [AFC 2023/24 official group-stage schedule PDF](https://assets.the-afc.com/2023-24_ACL/Downloads/AFC-Champions-League-Group-Stage-Draw-Results-%26-Match-Schedule.pdf)
- [AFC 2024/25 ACL Elite official schedule PDF](https://assets.the-afc.com/2024-25_ACL_Elite/Draw/Group_Stage/ACL-Elite-League-Stage---Draw-Results-%26-Match-Schedule.pdf)
- [AFC 2023/24 archive](https://www.the-afc.com/en/more/content/afc_champions_league_2023-2024_-_archive_download.html)

## Adapter grouping

1. **Legacy stats adapter:** 2015–2017, and linked samples in 2018–2021. It has the strongest identity model, but full-year listing must be proven from official links before collection.
2. **Mixed legacy/archive adapter:** 2018–2022. Official archives and technical reports supplement legacy match reports; coverage is not uniformly equivalent to a complete fixture listing.
3. **Modern fixture adapter:** 2023–2024. Official fixture PDFs and articles provide fields, but stable common match IDs are not consistently exposed. Derived keys are required where no official ID is present.

## Collection readiness

Immediate full collection readiness is limited to years where an official listing can enumerate every relevant match and every listing row has either a directly linked legacy report ID or complete official fixture fields. Based on this limited review:

- 2015 and 2019: ready for a dedicated legacy adapter pass.
- 2016–2018, 2020–2022: additional official listing verification required before full collection.
- 2023: mixed-source reconciliation required because calendar year crosses competition editions.
- 2024: modern fixture adapter with derived identity required; full uniqueness validation is still required.

No full-season crawl, CSV generation, TeamMaster modification, or third-party source was used for this matrix.
