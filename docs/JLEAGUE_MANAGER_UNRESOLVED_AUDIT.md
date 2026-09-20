# Unresolved manager identity audit

調査日：2026-09-20

対象は既存の2015–2024 manager historyのみ。2025・2026 match historyは使用していない。既存のSFIX06/SFIX07 cache、manager master、resolved historyをローカル確認し、追加network accessは行っていない。

## 1. Unresolved raw names

既存resolved historyでstaff_idがnullのhome/away appearanceを統合した。すべての未解決名にUnicode replacement character（`�`）が含まれている。

| raw manager name | appearances | teams | seasons | first match | last match |
|---|---:|---|---|---|---|
| `�y�g�����B�b�` | 334 | team_0023, team_0030 | 2015–2024 | 2015-03-07 | 2024-12-08 |
| `�b�{ �̎k` | 10 | team_0027 | 2021 | 2021-02-27 | 2021-04-14 |
| `�u���[�m �R���J` | 6 | team_0018, team_0029 | 2016, 2018, 2021 | 2016-09-25 | 2021-05-12 |
| `���� �[��` | 3 | team_0006 | 2022, 2023 | 2022-02-19 | 2023-07-08 |
| `�p�V�F�R` | 1 | team_0008 | 2021 | 2021-07-24 | 2021-07-24 |
| `�}���R�X �r�x�X` | 1 | team_0011 | 2020 | 2020-09-23 | 2020-09-23 |
| `�I�V ����` | 1 | team_0009 | 2024 | 2024-07-06 | 2024-07-06 |
| `���� �q` | 1 | team_0011 | 2024 | 2024-03-02 | 2024-03-02 |
| `���� ���` | 1 | team_0002 | 2022 | 2022-08-06 | 2022-08-06 |

合計は358 appearances、9 raw namesである。

## 2. Official master comparison

既存`data/processed/jleague_manager_master/managers.csv`に対して、公式日本語名のexact matchと許可済みwhitespace normalizationを確認した。英語名との一致も確認対象にしたが、raw historyには英語名がなく、replacement characterを含むため確定候補にはならなかった。

結果：

- deterministicに一致：0 raw names
- duplicate-name ambiguity：0 raw names
- replacement-character unresolved：9 raw names / 358 appearances
- その他未解決：0 raw names

SFIX07の年度別チーム情報を、壊れたraw nameを復元する根拠として推測利用することはしなかった。team + seasonだけでは、同一teamに複数の監督候補が存在し得るため、candidate staff_idを一意に確定できない。

## 3. Official evidence

確認済みの公式構造では、SFIX06の検索結果に公式日本語名、英語名、生年月日、国籍、SFIX07へのstaff_idリンクがある。SFIX07にはstaff_id単位の人物metadataと年度別成績がある。

- SFIX06: https://data.j-league.or.jp/SFIX06/
- SFIX07 example: https://data.j-league.or.jp/SFIX07/?staff_id=1357

しかし今回の9名は、手元のSFMS02由来raw文字列がreplacement characterに変換されている。正しい元の名前を公式source上で再現できないため、公式masterの候補を「同一人物」とするA/B/C条件は成立しない。よって公式根拠によるaliasは作成しなかった。

## 4. Alias decision

`data/master/manager_aliases.csv`は追加していない。

理由：

1. raw nameの情報がreplacement characterで失われている。
2. fuzzy matching、Levenshtein、文字削除、Unicode文字置換は禁止されている。
3. team + season associationだけではcandidate staff_idが一意にならない。
4. 「同一人物に見える」だけでstable IDを付与することはidentity accuracyを損なう。

したがって、resolved historyのrow count、match_id、team_id、chronologyは変更していない。

## 5. Stable-ID transition re-count

既存resolved historyのうち、前後appearanceの両方にstaff_idがあり、staff_idがexactに変化したtransitionだけを再集計した。未解決appearanceを跨いで推定していない。

| 指標 | 件数 |
|---|---:|
| stable-ID transitions | 239 |
| in-season | 158 |
| season-boundary | 81 |
| A→B→A | 18 |
| one-match manager | 18 |

以前のraw-name結果（269 / 182 / 87 / 26 / 26）から減少しているが、これは未解決appearanceを除外した結果であり、性能目的の統合やtransition削減ではない。

## 6. Final conclusion

今回の9 raw namesは、既存official masterと安全にstaff_id解決できなかった。解決できたraw name数は0、解決できなかったraw name数は9である。

resolved appearanceは6,058、resolved rateは94.42%、remaining unresolvedは358 appearancesで変更なし。

今後解決するには、SFMS02 raw cacheを正しいencodingで再取得できるか確認し、元の公式表示名を復元したうえで、SFIX06/SFIX07のstaff_idとteam/season associationを再検証する必要がある。その確認なしにmanual aliasを追加しない。
