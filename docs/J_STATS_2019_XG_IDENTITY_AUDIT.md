# 2019 J Stats `expected_goals` identity recovery audit

## Scope

対象は公式J.LEAGUE.jpの次の1ページだけ。

`https://www.jleague.jp/j1/stats/club/2019/expected_goals/search-list/`

他season、他stat、bulk materialization、feature/model処理は対象外とした。

## Response and parser path

- HTTP status: 200
- final URL: requested URLと一致
- content type: `text/html; charset=utf-8`
- response size: 800,921 bytes
- embedded format: Next.js `self.__next_f.push(...)` 内のJSON payload
- ranking object: `ranking-expected_goals`, category `j1`, year `2019`
- ranking rows: 18
- response raw bytesにUTF-8 replacement sequence `EF BF BD`: 0
- UTF-8 strict decode後の U+FFFD: 0

RSC payloadをJSONとしてstrictに読み、ranking rowの `club`、`href`、`code`、`name`、icon fieldsを確認した。

## Identity coverage

| Identity field | Coverage | Uniqueness / finding |
|---|---:|---|
| ranking row | 18/18 | rank 1–18の18 rows |
| official club name (`club.name`) | 18/18 | 18 unique names |
| TeamMaster exact `jleague_official` mapping | 18/18 | 18 unique stable `team_id` |
| `href` | 15/18 | 3 rowsはfieldなし |
| `club.code` | 15/18 | 3 rowsは空文字 |
| numeric club ID | 0/18 observed | なし |
| separate club master/lookup ID | 0/18 observed | 同一payload内で未確認 |
| image URL | 18/18 | common sprite URL。club identityには不採用 |

`href` と `club.code` が存在する15 rowsでは、値は一致するslug形式だった。空だった3 rowsにもofficial `club.name` とicon sprite metadataは存在したが、sprite URL・座標・slotをstable club IDとして採用しない。

## TeamMaster exact cross-reference

18件すべてについて、responseの `club.name` をそのまま `source=jleague_official` で既存TeamMasterへexact resolveした。

- TeamMaster exact resolved: 18/18
- unresolved: 0
- duplicate team IDs: 0
- one response name to multiple team IDs: 0
- manual assignment: 0
- fuzzy/substring/normalization recovery: 0

この結果により、code/hrefが空の3 rowsも、公式club nameと既存official TeamMaster aliasのexact mappingで安全にidentityを確定できる。新しいalias、new team ID、club codeの推測生成は不要である。

## Encoding finding

今回のraw responseではreplacement characterは発生していない。HTTP headerはUTF-8を明示し、UTF-8 strict decodeで18件の日本語official nameが保持された。

前回の確認時に見えた `�` はresponse bytesやparser outputではなく、PowerShell/端末出力時のencoding表示によるmojibakeだったと判断する。したがってdecode方式を変更していない。raw bytesからの再decode、名称修復、Unicode置換によるidentity推測は行っていない。

## Alternative identifier assessment

このpageから18/18で利用できるsafe identity keyは、次の複合的なexact evidenceである。

```text
official response club.name
    -> existing TeamMaster source=jleague_official exact alias
    -> unique stable team_id
```

15/18では加えてofficial `href`/`club.code`を保存できる。残り3件についてhref/codeを新規生成せず、materialized artifactにはraw official name、resolved `team_id`、空のofficial club code/hrefを明示保存する。

## Verdict

**A: official exact identityで18/18安全に復元可能。**

2019 `expected_goals` pageは、stable code/hrefのcoverage自体は15/18だが、全18 rowsにlossless official nameがあり、既存TeamMasterのofficial exact mappingが18/18で成立する。従って、historical materializationはこのidentity policyで再開可能である。

ただし本監査は1 pageのみの確認であり、他season/statへこの結果を自動一般化しない。materializerは各pageで同じstrict条件を再検証し、空name、空code、unresolved、duplicate team/stat、unexpected club countをhard failにする。

## Out of scope

- bulk historical acquisition
- processed artifact生成
- feature dataset生成
- model fitting/evaluation
- prediction
- TeamMaster変更
- fuzzy recovery
- commit/push
