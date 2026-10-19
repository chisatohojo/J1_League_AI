# Phase 2.1 研究artifact・予測・監査の契約

形式はUTF-8 JSON。Python側の厳密な検証器は [nn_v2_contracts.py](../../../src/modeling/nn_v2_contracts.py)、NN数値artifactの読込検証は [nn_residual_v2.py](../../../src/modeling/nn_residual_v2.py)。未知・不足field、NaN/Inf、不正クラス等は拒否する。新規schema用ライブラリは導入しない。

この工程で実装した将来予測・登録の関数は**辞書を検証するだけ**であり、登録・ファイル保存・公式取得・実時計の偽装をする機能はない。合成例のT0・公式ID・SHAは架空で、実在する証拠の代用には使わない。

## 1. NN数値artifact

schema=`nn_v2_residual_artifact_v1`、role=`research_only_not_champion`。

| field | 契約 |
|---|---|
| specification | [NUMERICS.md](NUMERICS.md)とコードのspecification()の完全一致。数値型も維持 |
| versions | Python/NumPy/pandas/sklearnの実際の版。別版での読込は停止 |
| theta | row-majorのW1/b1/W2/b2、正確に90個の有限float64 |
| feature_order / classes | Form8列の固定順序、[0 Away,1 Draw,2 Home] |
| scaler | mean/var/scaleが各8要素。var非負、scale正、定数列の規則を含め整合 |
| training_rows | 3以上の整数。合成artifactの件数を実データの2,976件と誤認しない |
| epochs / loss_curve | 正確に200、更新後の有限・非負の損失200点 |

saveは未作成ディレクトリにartifact.jsonとartifact.sha256だけをcreate-newし、flush/fsync/readbackする。loadでは外部manifest等に固定したexpected_sha256を必須とする。sidecarと本体を両方変更しても、外部pinが一致しなければ拒否する。JSON重複キー・余分なファイル・不正状態も拒否する。pickleは使用しない。

この数値artifactだけでは訓練データの来歴や実時計は証明できない。実データで使うには次のstudy manifestと実入力監査が別途必要。

## 2. 研究全体のartifact manifest

schema=`nn_v2_study_artifact_manifest_v1`。validate_artifact_manifestで検証する。

- roleはresearch_only_not_champion、data_originはsynthetic/realを明示し、study_idを持つ。
- residual_sha256、baseline_sha256、implementation_sha256、spec_sha256、training_manifest_sha256、input_sha256の全値は64桁小文字hex。
- feature_order、class_order、timing_policyは固定契約。source_rows > residual_rows > 0。
- realの場合はsource_rows=3,588、residual_rows=2,976を要求する。syntheticの場合は独立した小さい件数を許す。
- sealed_atはtimezone付き日時。

FinalBaselineとCrossfitOffsetsは別型・変更不能なrole fieldで区別する。cross-fitの監査には対象年・訓練年/ID・対象ID・Scaler実学習件数/統計・クラス・係数を含む。将来推論用の最終基準をcross-fit値と称して保存しない。基準pipelineの永続化・実source証拠との結合を行う実データ実行入口は本工程では作っていない。

## 3. 将来対象のproposal

schema=`nn_v2_enrollment_proposal_v1`、state=proposal、competition=2026_27_ordinary_J1。

study_id、data_origin、t0、spec_frozen_at、artifact_sealed_at、schedule_observed_at、official_revision、r_start、fixturesを必須とする。

- spec_frozen_at <= artifact_sealed_at <= T0 <= 外側now、schedule_observed_at <= T0。
- roundは連続20節、各10試合、合計200試合。各節の20クラブ集合は一致、節内のクラブ重複なし。
- fixtureはfixture_key、round、home/away ID、kickoff、status、namespace、official_id、mapping_statusを持つ。
- kickoffは外側nowより厳密に後。status=scheduled、namespace=jleague_match_page。
- ID未登録はofficial_id=null/mapping_status=pendingのまま追跡可能。ID推測で補わず、そのfixtureの予測は拒否する。確認済みIDは文字列の数字列、衝突禁止。

validate_enrollmentは構造・T0を検証する。**validate_target_selectionも必須**で、別入力の全38節380試合を使い、R_startがT0時点で全試合未開始の最初の公式節であること、200fixtureのidentityがそのsourceと完全一致することを確認する。対象200件だけから自分で「最初の節」を証明しない。実公式parser・publication/SHAとの照合、実時計の外側receipt、実登録writerは未接続であり、この検証だけをもって実登録成功としない。

## 4. paired予測

schema=`nn_v2_paired_prediction_v1`、prediction_type=research_v2_saved_pre_match。

- data_origin、study_id、model_version、run_id、登録fixture全情報。
- generated_at、readback_at、history_cutoff、source_observed_at。
- official_revision、source_witness_sha256、baseline_sha256、residual_sha256、feature_schema_sha256。
- class_order=[0,1,2]、base_probabilitiesとresidual_probabilitiesは各3個、有限・0〜1・合計1（絶対誤差1e-12以内）。

T0 <= generated_at <= readback_at < kickoff、source_observed_at <= generated_at、history_cutoffは対象JST日付の00:00。fixtureはproposalと完全一致し、ID確認済みでなければならない。score/result等の余分なfieldは拒否する。日付batchはその日の登録対象の完全集合で、重複・混在日付・部分成功を拒否する。全readbackがbatch最早kickoffより前であることも検証する。

時刻比較はUTC整数100nsで行い、小数秒7桁目を保持する。日時の桁数超過、無効日付、naive時刻、不正offset、未知offsetを示す-00:00は拒否する。datetimeによるmicrosecond変換は日付groupingだけに使用し、締切比較には使わない。

実際のappend-only保存、生成終了時の実時計取得、receipt、source訂正/延期の再照合は未接続。現在の関数は検証だけで、実際の将来予測ファイルは0件。

## 5. Phase 2.1監査manifest

schema=`nn_v2_phase2_1_audit_v1`、data_origin=synthetic。study_id、started_at/finished_at、implementation_sha256、artifact_manifest_sha256、source_hashes、checksを持つ。

checksの各値はPASS/FAIL/NOT_RUNを区別する。real_fit_calls、real_evaluation_calls、future_saved_predictionsはすべて整数0を要求する。これは合成工程の契約であり、将来の実データrunの成功記録へ流用しない。

Phase A: BLOCKED / Phase B: NOT_AUTHORIZED。
