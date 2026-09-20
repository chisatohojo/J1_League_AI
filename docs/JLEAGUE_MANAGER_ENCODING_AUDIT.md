# J.League manager encoding audit

調査日：2026-09-20

対象は2015–2024の既存cacheとmanager historyのみ。network access、2025/2026 match history、名前推測、fuzzy matchingは行っていない。

## 1. 結論

未解決9 raw name、358 appearancesに対応するSFMS02 raw HTMLのA10 manager areaを元bytesで確認した。対象`td.name`のbyte sliceは、9名すべてUTF-8としてlossless decodeできた。CP932、Shift-JIS、EUC-JPは対象byte列に対して日本語公式名として成立せず、置換文字・文字化けを含む結果になった。

ただし、UTF-8 decode結果を既存manager masterのofficial_name / official_english_nameへexact一致させ、かつteam/season associationを一意に確認できる候補は0件だった。したがって安全に復元・解決できたname数は0、collector変更も0件である。

CSV表示上のreplacement characterから人物を推測せず、raw bytesから復元したUTF-8名を調査したが、official masterに無い名前をteamだけでstaff_idへ割り当てることは行わなかった。

## 2. Per-name encoding audit

下表のsample match_idは、各raw nameの代表的なSFMS02 cacheである。byte representationは対象manager名のbyte列を確認したもの。全9件でUTF-8はvalid、他の候補はofficial nameとして採用不可だった。

| Raw name（UTF-8復元） | Appearances | Sample match_id | UTF-8 | CP932 | Shift-JIS | EUC-JP | Official master exact | Confidence |
|---|---:|---|---|---|---|---|---|---|
| ペトロヴィッチ | 334 | 16810 | valid | invalid/garbled | invalid/garbled | invalid/garbled | No | unresolved |
| ブルーノ コ​​ンカ | 6 | 18156 | valid | invalid/garbled | invalid/garbled | invalid/garbled | No | unresolved |
| マルコス ビベス | 1 | 24049 | valid | invalid/garbled | invalid/garbled | invalid/garbled | No | unresolved |
| 甲本 偉嗣 | 10 | 24978 | valid | invalid/garbled | invalid/garbled | invalid/garbled | No | unresolved |
| 迫井 深也 | 3 | 27333 | valid | invalid/garbled | invalid/garbled | invalid/garbled | No | unresolved |
| 高橋 大輔 | 1 | 27538 | valid | invalid/garbled | invalid/garbled | invalid/garbled | No | unresolved |
| 菅原 智 | 1 | 30442 | valid | invalid/garbled | invalid/garbled | invalid/garbled | No | unresolved |
| 栗澤 僚一 | 1 | 30646 | valid | invalid/garbled | invalid/garbled | invalid/garbled | No | unresolved |
| パシェコ | 1 | 24989 | valid | invalid/garbled | invalid/garbled | invalid/garbled | No | unresolved |

「ブルーノ コンカ」の空白など、表示上の空白差があり得る名前についても、許可されたwhitespace normalization後にofficial masterへ一意一致しなかった。中黒除去、文字削除、類似度判定、別人候補の推測はしていない。

## 3. Raw byte and HTML inspection

各sampleについて、次の構造だけを対象にした。

```text
A10 manager area
  two-column-table-box-l / two-column-table-box-r
    td.name
```

HTML全体のContent-Type宣言はUTF-8で、対象manager byte sliceもUTF-8の日本語byte patternだった。BOMに依存せず、対象sliceを直接decodeした。ページ全体をCP932へdecodeし直す処理は行っていない。

各候補の判定は次の順序で行った。

1. raw HTML bytesから対象`td.name` sliceを取得
2. UTF-8 / CP932 / Shift-JIS / EUC-JPを対象sliceだけに適用
3. losslessかつreplacement characterを含まないdecode結果を確認
4. 公式masterのofficial_name / official_english_nameへexactまたはwhitespace-only一致を確認
5. team/seasonで候補が一意か確認

UTF-8以外を採用する根拠は得られなかった。

## 4. Resolution result

| 指標 | 結果 |
|---|---:|
| Raw unresolved names | 9 |
| Unresolved appearances | 358 |
| Raw byteからsafe decodeできたname | 9 |
| Official masterへsafe resolutionできたname | 0 |
| Newly resolved appearances | 0 |
| Remaining unresolved appearances | 358 |
| Total appearances | 6,416 |
| Resolved appearances | 6,058 |
| Resolved rate | 94.42% |

既存のresolved CSVは再生成していない。row count 3,208、match_id、team_id、chronologyも変更していない。

## 5. Collector and regression decision

collector変更なし。理由は、raw bytesからのUTF-8復元自体は可能だったが、今回の安全条件であるofficial masterへの一意exact matchとteam/season associationを満たすnameが0件だったためである。

既存の正常なUTF-8 manager名を変更・破壊するdecode fixは不要だった。既存collectorの全体decode方式を変更していないため、2015/2019/2024 sampleの既存出力も変更していない。

## 6. Final decision

今回の9名は「raw bytesから名前を復元できない」のではなく、「raw bytesからUTF-8名は復元できるが、現在のofficial manager masterだけではstable staff_idへ安全に対応付けられない」と結論する。

今後必要なのは、SFIX07のhistorical associationをstaff_id候補ごとに公式に確認する作業である。ただし、候補staff_idを名前類似やteam単独で選ばない限り、今回の入力だけからは自動解決できない。
