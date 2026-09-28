# 2024 official player identity linkage prototype

調査日: 2026-09-28

## Verdict

**`DEFER_HISTORICAL_PLAYER_ENUMERATION`**

J.League Data Site の公式 `SFPR01` は、2024 J1 のclub-season選手を
0出場者込みで再現可能に列挙する。しかし3クラブすべてで選手行に
`player_id` / `SFIX04` linkがなく、列挙された名前をstable official IDへ
一括で結ぶことはできなかった。J.LEAGUE.jpの2024名鑑告知からのclub linkは
現在のrosterへ遷移し、2024状態を保持していない。

3クラブのSFMS02表示名はSFPR01表示名と103/103でexact一致したが、これは
**name coverage**であって**identity coverage**ではない。ID-bearing
club-season enumerationが0件なので、official-ID `EXACT`は0件とする。
個別profileを名前検索して埋めるcrawl、名前正規化、current clubからの逆算は
行っていない。

この判定はidentity dataset側のblockerである。registration effective dateも
別途未解決だが、今回のroot blockerはそれより前のhistorical ID enumerationで
ある。model、feature、prediction、metricは実行していない。

## 1. Source-of-truth constraints

既存監査どおり、SFMS02 A5/A6/A7/A9のplayer rowにはprofile linkやstable
player IDがない。2024 squad rowsは既存
`data/processed/sfms02_player_minutes/2015_2024_j1_player_minutes.csv`を
read-onlyで使用した。TeamMasterはclubのexact identityだけに使用し、変更して
いない。

Data Siteの個別 [`SFIX04`](https://data.j-league.or.jp/SFIX04/?player_id=11446)
にはnumeric `player_id`があり、同一profile内の複数season/club evidenceもある。
しかし個別profileの存在は、あるclub-seasonの全選手をID付きで列挙できることを
証明しない。Data Site IDとJ.LEAGUE.jp IDも別namespaceのままである。

## 2. Enumeration gate

### Official routes inspected

1. Data Siteの公式メニューから
   [選手出場記録 SFPR01](https://data.j-league.or.jp/SFPR01/)へ進むと、season、
   competition、clubを選ぶ公式画面がある。
2. 検索エンジンで既にindexされたData Site公式結果から、次の2024 J1 exact
   result URLを確認した。competition/player IDや非公開endpointを推測していない。
3. [2024選手名鑑公開告知](https://www.jleague.jp/news/article/27175/)のclub別
   「選手名鑑」linkは現在のclub rosterへ遷移した。2024 snapshotではない。
4. `SFIX02`はcurrent登録一覧でseason selectorがなく、`SFIX03`は公式画面に
   「Jリーグ最終所属チーム」で検索すると明記されている。どちらも2024
   club-season ID enumerationの代替にしない。

### Selected clubs

| Club | TeamMaster ID | Selection reason | Official 2024 result |
| --- | --- | --- | --- |
| セレッソ大阪 | `team_0002` | 通常club。既存監査でSFMS02 `レオ　セアラ`とSFIX04 profile heading `レオ　セアラ（レオナルド）`の表記差を確認済み | [SFPR01 C大阪](https://data.j-league.or.jp/SFPR01/search?competition_frame_id=1&competition_frame_id_ex=1&competition_id=589&competition_id_ex=589&competition_year=2024&competition_year_ex=2024&dataSize=1&pageStartNo=0&selectedCompetitionName=%EF%BC%AA%EF%BC%91%E3%83%AA%E3%83%BC%E3%82%B0&selectedCompetitionYear=2024%E5%B9%B4&selectedTeamName=%EF%BC%A3%E5%A4%A7%E9%98%AA&team_id=20&team_id_ex=20) |
| ガンバ大阪 | `team_0005` | 既知の同名別人 `松田　陸` を含み、collisionをfail-closedで確認できる | [SFPR01 G大阪](https://data.j-league.or.jp/SFPR01/search?competition_frame_id=1&competition_frame_id_ex=1&competition_id=589&competition_id_ex=589&competition_year=2024&competition_year_ex=2024&dataSize=1&pageStartNo=0&selectedCompetitionName=%EF%BC%AA%EF%BC%91%E3%83%AA%E3%83%BC%E3%82%B0&selectedCompetitionYear=2024%E5%B9%B4&selectedTeamName=%EF%BC%A7%E5%A4%A7%E9%98%AA&team_id=9&team_id_ex=9) |
| サガン鳥栖 | `team_0029` | 3標本中最多の43表示選手。公式[2024 transfer一覧](https://www.jleague.jp/j1/special/transfer/search-list/?year=2024)にもseason中INが複数あり、登録変化を含む | [SFPR01 鳥栖](https://data.j-league.or.jp/SFPR01/search?competition_frame_id=1&competition_frame_id_ex=1&competition_id=589&competition_id_ex=589&competition_year=2024&competition_year_ex=2024&dataSize=1&pageStartNo=0&selectedCompetitionName=%EF%BC%AA%EF%BC%91%E3%83%AA%E3%83%BC%E3%82%B0&selectedCompetitionYear=2024%E5%B9%B4&selectedTeamName=%E9%B3%A5%E6%A0%96&team_id=33&team_id_ex=33) |

各SFPR01 pageは `2024/12/08 更新` と表示し、season-finalの選手出場記録を
提供する。保存せずin-memoryで確認したraw HTMLでは、3 pageすべて
`th.name-c` player cellsを持つ一方、`player_id` tokenと`SFIX04` tokenは
いずれも0だった。したがって必要項目のうちofficial name、club、season、
source URLは得られるが、**official player IDだけが欠ける**。

## 3. Coverage audit

### Club-season unique raw-name keys

| Club | SFMS02 unique raw keys | SFMS02 player-match rows | Official display players | ID-bearing official players | Exact display-name intersection | EXACT | UNRESOLVED | AMBIGUOUS | COLLISION | NAME_VARIANT diagnostic | Official-ID linkage rate |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| C大阪 | 31 | 684 | 34 | 0 | 31 | 0 | 31 | 0 | 0 | 1 | 0/31 (0%) |
| G大阪 | 31 | 684 | 35 | 0 | 31 | 0 | 30 | 0 | 1 | 0 | 0/31 (0%) |
| 鳥栖 | 41 | 684 | 43 | 0 | 41 | 0 | 41 | 0 | 0 | 0 | 0/41 (0%) |
| **Total** | **103** | **2,052** | **112** | **0** | **103** | **0** | **102** | **0** | **1** | **1** | **0/103 (0%)** |

`unique raw keys`は `(season, team_id, player_name_raw)` 単位である。3 clubの
distinct raw stringは102だが、`清武　弘嗣`がC大阪と鳥栖の両方に現れるため
club-season keyは103になる。同一人物のseason中移籍に見えても、official ID
なしに2 keyをmergeしない。

`NAME_VARIANT diagnostic=1`は `レオ　セアラ`。SFPR01とSFMS02はexact一致
する一方、既存監査で確認済みのSFIX04 headingは括弧内名を含む。これは
UNRESOLVED 31件の内数であり、括弧除去・NFKC・空白除去によるID確定はしない。

`COLLISION=1`はG大阪の `松田　陸`。既存公式profile evidenceに別人物の
Data Site IDs `11446` / `29236`がある。今回のSFPR01 row自身はIDを持たない
ため、club/nameから一方を推測せずCOLLISIONとした。

### Player-match row view

| Status | Rows | Note |
| --- | ---: | --- |
| EXACT | 0 | ID-bearing enumerationがない |
| UNRESOLVED | 2,038 | `レオ　セアラ` 38 rowsをname-variant diagnosticとして含む |
| AMBIGUOUS | 0 | 候補ID集合自体を安全に列挙できないため、0を「曖昧性なし」と解釈しない |
| COLLISION | 14 | 2024 G大阪 `松田　陸` squad rows |

同じ選手の複数appearanceはunique coverageに重複計上せず、player-match row
coverageは別表にした。Starting XIだけでなく、全38 match × 18 squad rows ×
3 clubsを基準にしている。

## 4. Exact-linkage and collision contract

`src/collect/player_identity_prototype.py`はnetworkを使わないprototype helperで
あり、次を強制する。

- keyはexact `(season, team_id, player_name_raw)`だけ。
- official recordはnamespace込みのData Site `player_id`と、それと一致する
  official `SFIX04` URLを必須とする。
- 1 scoped official IDだけなら`EXACT`、0件なら`UNRESOLVED`、複数なら
  `AMBIGUOUS`、known same-name collisionなら`COLLISION`。
- internal player IDを発行しない。
- NFKC、空白除去、fuzzy、surname、shirt number、birth date、current club、
  manual aliasを使用しない。
- unique player keyとplayer-match rowのstatus countsを分ける。

fixture testsでは `セルジーニョ` (`29580` / `23156`) と `松田　陸`
(`11446` / `29236`) を異なるofficial IDのまま保持し、raw名だけでmergeしない。
またASCII spaceと全角spaceの差を自動解決しない。

SFPR01 parserは表示名cellと、そのcell内に**実在する場合だけ**SFIX04 ID linkを
読む。今回の縮小fixtureも実ページ同様ID linkを持たず、
`id_enumeration_complete=False`となる。将来source structureが変わった場合も、
IDを捏造せず再監査できる。

## 5. Historical roster semantics

今回確認したSFPR01はseason-final `2024/12/08 更新` pageであり、各target
kickoff前のas-of roster snapshotではない。0出場者を含むことはfull registration
ledgerや有効期間の証拠でもない。official transfer一覧の日付も、個別登録の
effective timestampまたは後日訂正履歴と同義ではない。

従って次の2 gateは分離し、両方未通過とする。

| Gate | Result |
| --- | --- |
| Stable identity linkage | **DEFER** — club-season ID-bearing enumerationがない |
| Point-in-time registration validity | **DEFER** — explicit加入/抹消有効期間とhistorical as-of snapshotがない |

identity gateが将来通っても、registration effective-date gateを通るまでPIT roster
feature readyとは判定しない。

## 6. Artifact and request discipline

Enumeration gateが成立しなかったため、
`data/processed/player_identity_prototype/2024_sample_player_identity.csv`は作成
していない。production collector、production player master、TeamMaster変更もない。

外部確認は公式 `jleague.jp` / `data.j-league.or.jp`だけに限定した。代表3 clubの
SFPR01 result、公式menu、2024名鑑告知、既存公式profile/collision evidenceだけを
使用し、20 club crawl、numeric ID総当たり、individual player crawl、非公式source、
推測endpointは使用していない。取得ページはin-memory監査のみでraw artifactを
新規保存していない。

## 7. Exit criteria

`PROCEED_TO_PLAYER_IDENTITY_DATASET_SPEC`へ進むには、公式画面から再現可能に
辿れる2024 club-season routeが、全列挙playerについてofficial player ID、official
display name、club、season、profile URLを同じrecordで提供する必要がある。
個別profile検索の寄せ集めや名前ベース補完では代替しない。その後、SFMS02 exact
linkage coverageを再計測し、identity datasetとPIT registration ledgerを別成果物と
してfreezeする。
