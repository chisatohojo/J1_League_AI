# 状態遷移と停止境界

```mermaid
flowchart TD
    N[新規オフラインrun] --> C[exclusive-create開始claim]
    C --> A[Stage A: 原本・HTTP記録・identity・結果検証]
    A -->|不整合・unknown HTML| S[全体STOP]
    A -->|事実と証拠が成立| F[原本bundleを書込み・fsync・readback・seal]
    F -->|保存失敗| S
    F --> B[Stage B: 封印bytesだけを再読・備考審査]
    B -->|SHA・identity・結果不整合| S
    B -->|既知契約PASS| P[詳細PASS・history admission false]
    B -->|未知備考・未分類時刻| Q[隔離HOLD・history admission false]
    P --> R[packet・解析・seal・receiptを保存し全SHA再検証]
    Q --> R
    R -->|失敗・未確定| S
    R -->|確定後のみ| X[次の保存済み入力]
    X --> A
```

停止したrunも異常終了したrunも、開始claimの存在により再実行を拒否する。停止後に残る入力へ進まず、再開用の入口を持たない。raw、metadata、request、sealとreceiptは上書きしない。

Stage Aで原本封印が完了しStage Bが備考HOLDとなることは、全体STOPとは区別する。隔離receiptを確定できる場合だけ後続のオフライン処理を続行する。Stage Aでidentityや結果を検証できない異常を、備考HOLDに置き換えない。Stage Bでも同じstrict結果を要求し、不整合を隔離対象として隠さない。

取得状態、詳細解析状態、隔離状態、時刻証拠状態、履歴採用状態を分ける。正常終了や詳細全件PASSもHISTORY/PREDICTIONのREADYを意味せず、隔離中の試合を無視した履歴出力も行わない。
