# Champion A Season Transition Evaluation Result

Formal status: COMPLETE

Reused historical RESEARCH SCREEN, not unseen confirmation, causality, or a new Champion.

## Provenance and pre-fit gates

Source/master/OOF/schema/identity/chronology/runtime/ST0 reference gates: PASS.

~~~json
{
  "execution_head": "122034348aa2a0d3e863832503c0cbfd8b34d518",
  "authorization": {
    "approved_execution_head": "122034348aa2a0d3e863832503c0cbfd8b34d518",
    "task_reference": "champion-a-season-transition-formal-evaluation-approved-2026-10-06"
  },
  "spec_commit": "88b6d28ac12ae2232f29d5084e8d9ebf395292a9",
  "spec_sha": "efbf7995d2a8f5611d4002f5f9fe2299201d1d24c6e100dbf8662081e163cdd2",
  "evaluator_sha": "4c7a32be6d8f9d850c52b974bfb4d3117fb0ff8ba7ba6c908cd50ece5b27d32e",
  "input_hashes": {
    "data/processed/jleague/2015_matches_probe.csv": "ea0ab9e1788373702d9ce425f83c74bae21a7afd35752d9c24481f4bc9400353",
    "data/processed/jleague/2016_matches_probe.csv": "4a3bcd4f0beaa20192abc60071e5153c846c1ca132b1876d174a2e46a5dde45f",
    "data/processed/jleague/2017_matches_probe.csv": "d2f8ae9959762d172c4afb209e1916afd2dfadbcb0955a99b281aab2fb07f59b",
    "data/processed/jleague/2018_matches_probe.csv": "f6d90f5dec3461fca230ca487233c63273fb69156970af3940d32b1455672681",
    "data/processed/jleague/2019_matches_probe.csv": "3b2090ec38e064457ec4ae0f9981ae457350af268f75886150b6f05d95d6fe2f",
    "data/processed/jleague/2020_matches_probe.csv": "fd295aca0097ee0041659cdbe42ec9375227969e9b0c51efa8993753cccbfe17",
    "data/processed/jleague/2021_matches_probe.csv": "298c3d4c4eb66fa6d6d00748e19382e5f304899355297acdbf42f251e11114b6",
    "data/processed/jleague/2022_matches_probe.csv": "d4861930524d5e171b3c93f18361af7b17c6055ae27d9055a6e9a9ab266ba2c2",
    "data/processed/jleague/2023_matches_probe.csv": "6a1e002dd7e9d0187d014e517057ad3d79430eece66fcb6b5239e9db590085c9",
    "data/processed/jleague/2024_matches_probe.csv": "4b2fa48f762e04316c7ded093d3919642d62d3c2b5edc92a55e012cf6ce410d1",
    "data/master/teams.csv": "ec255eb65e9fa2c310e3fbcfeecf7a7d201ca4f458a15bb0d129fa0ca9e1b89f",
    "data/processed/model_diagnostics/champion_a_oof_2020_2024.csv": "cd8157303789fe2e929ccb74aeaabab09fa3c1a3a26338b10addaa2183a74f59",
    "data/processed/model_diagnostics/champion_a_oof_2020_2024_manifest.json": "b66f0fd9707e8d8835fcaec98962014e245296e97bd664f337b2e85066409f10"
  },
  "runtime": {
    "python": "3.12.14",
    "platform": "Windows-11-10.0.26200-SP0",
    "numpy": "2.5.3",
    "pandas": "3.0.5",
    "scipy": "1.18.1",
    "scikit-learn": "1.9.1",
    "requirements_sha256": "887f566527f6a10da4e1ac6fcfc66810634c5e82f0ddc2b232084c9880753eda",
    "lock_sha256": "3aea21392b63f9fc3dfbcf00e44cb825a3eb7453d130492dde8bcb5da14ddc04"
  },
  "st0_reference": {
    "2020": {
      "n": 306,
      "accuracy": 0.5065359477124183,
      "log_loss": 1.023119734659012,
      "brier": 0.6117572218710644
    },
    "2021": {
      "n": 380,
      "accuracy": 0.5078947368421053,
      "log_loss": 1.0253437210487792,
      "brier": 0.6149829138674616
    },
    "2022": {
      "n": 306,
      "accuracy": 0.4019607843137255,
      "log_loss": 1.0940186385371449,
      "brier": 0.6610224339161608
    },
    "2023": {
      "n": 306,
      "accuracy": 0.46078431372549017,
      "log_loss": 1.0604285568595655,
      "brier": 0.638530529273072
    },
    "2024": {
      "n": 380,
      "accuracy": 0.45,
      "log_loss": 1.079241181120235,
      "brier": 0.6531695943664019
    },
    "pooled": {
      "n": 1678,
      "accuracy": 0.466626936829559,
      "log_loss": 1.056065401323764,
      "brier": 0.6357323419292724
    }
  },
  "marker_path": "data/processed/model_season_transition/formal_season_transition_attempt.json",
  "marker_sha": "89dfe53743b291b6be45284c9f035ead2b419f4a96a197bd84b35bdebad104cf",
  "marker_state": "ATTEMPT_CONSUMED"
}
~~~

## Frozen state and replay rules

Initial1500 / HA175 / scale400 / raw elo_diff without HA / 90-minute result / date-batched reads before updates.
ST0=saved accepted p, ZERO replay/fit/prediction; ST1=carry0.75,K30; ST2=carry1,K45 iff either ordinal<=5 else30; ST3=both.
All population IDs shrink once at every2016-2024 boundary for ST1/ST3, including absent teams. Ordinals reset each season.

~~~json
{
  "fold_identities": [
    {
      "year": 2020,
      "training_n": 1530,
      "validation_n": 306,
      "training_ids_sha256": "65b199341adc5ff9c7fc9c09dcfd73b1c4087e5d4f73cd71571fd4a69cddb158",
      "validation_ids_sha256": "66e2faeb3a51f0ea8e49bd76d1c484d191054997d8753c5acbc8663d3bbf1d35"
    },
    {
      "year": 2021,
      "training_n": 1836,
      "validation_n": 380,
      "training_ids_sha256": "a5a1265db672da0747a01fe0a69ab548ae684871be4f45efc4d1d1563e4ea266",
      "validation_ids_sha256": "9cd6cfa337ffb0477108775595a56bedb1edca7d05c4f099888bad54f41ded1e"
    },
    {
      "year": 2022,
      "training_n": 2216,
      "validation_n": 306,
      "training_ids_sha256": "dcd657ec4693b73a32fc27a6ee3dfc6b4c7c6efcde0c90328cdaeed9ce4b6cab",
      "validation_ids_sha256": "970c316240ee1597bf823d90711995bce334ba3e767f24d6c2d971088fc11803"
    },
    {
      "year": 2023,
      "training_n": 2522,
      "validation_n": 306,
      "training_ids_sha256": "405d0a8913098d6509381825a2299f494649b804af4528585d200e85c8c7013d",
      "validation_ids_sha256": "7a7e5f5dbf26a0ba046dbf8a59a441a05df535bd9b3730299e2e2b2bc9f46cc9"
    },
    {
      "year": 2024,
      "training_n": 2828,
      "validation_n": 380,
      "training_ids_sha256": "54a43cb0b98414d0768f1ad55f4e2adf474cf154080b0af1043792bed8f2304a",
      "validation_ids_sha256": "40ccf48bbadc5398d54f11e79f9f2c5f1e914a4ecede086caa3eef77dd72d915"
    }
  ],
  "boundary_seasons": {
    "ST1": [
      2016,
      2017,
      2018,
      2019,
      2020,
      2021,
      2022,
      2023,
      2024
    ],
    "ST2": [],
    "ST3": [
      2016,
      2017,
      2018,
      2019,
      2020,
      2021,
      2022,
      2023,
      2024
    ]
  },
  "counts": {
    "stage": "frozen selection",
    "replay_attempts": 3,
    "replays_completed": 3,
    "fit_attempts": 15,
    "fits_completed": 15,
    "scaler_fits_completed": 15,
    "prediction_attempts": 15,
    "predictions_completed": 15,
    "fold": 2024
  },
  "automatic_retries": 0,
  "st0_replays": 0,
  "st0_fits": 0,
  "st0_predictions": 0,
  "winner_refits": 0
}
~~~

## Training-only scaler/classifier and convergence evidence

### ST1

~~~json
{
  "2020": {
    "training_n": 1530,
    "scaler_mean": [
      6.0642483790189
    ],
    "scaler_var": [
      10352.070924676722
    ],
    "scaler_scale": [
      101.74512727731349
    ],
    "scaler_n_samples_seen": 1530,
    "classes": [
      0,
      1,
      2
    ],
    "coef": [
      [
        -0.29754116385282886
      ],
      [
        0.006339031471927031
      ],
      [
        0.2912021323809028
      ]
    ],
    "intercept": [
      0.09129553141303033,
      -0.29779476418771,
      0.20649923277468651
    ],
    "n_iter": [
      4
    ],
    "convergence_warning": false,
    "classifier_params": {
      "C": 1.0,
      "solver": "lbfgs",
      "max_iter": 1000,
      "random_state": 0
    }
  },
  "2021": {
    "training_n": 1836,
    "scaler_mean": [
      6.288582401899468
    ],
    "scaler_var": [
      11347.941407662232
    ],
    "scaler_scale": [
      106.52671687263356
    ],
    "scaler_n_samples_seen": 1836,
    "classes": [
      0,
      1,
      2
    ],
    "coef": [
      [
        -0.2985136328521976
      ],
      [
        -0.017664784968177142
      ],
      [
        0.3161784178203747
      ]
    ],
    "intercept": [
      0.10762069457297152,
      -0.3038901985056387,
      0.1962695039326591
    ],
    "n_iter": [
      4
    ],
    "convergence_warning": false,
    "classifier_params": {
      "C": 1.0,
      "solver": "lbfgs",
      "max_iter": 1000,
      "random_state": 0
    }
  },
  "2022": {
    "training_n": 2216,
    "scaler_mean": [
      5.806530991217867
    ],
    "scaler_var": [
      12398.508026618623
    ],
    "scaler_scale": [
      111.34858789683246
    ],
    "scaler_n_samples_seen": 2216,
    "classes": [
      0,
      1,
      2
    ],
    "coef": [
      [
        -0.31191219453348434
      ],
      [
        -0.03401405391463122
      ],
      [
        0.34592624844811615
      ]
    ],
    "intercept": [
      0.08888782499272668,
      -0.29063302249613765,
      0.2017451975034205
    ],
    "n_iter": [
      4
    ],
    "convergence_warning": false,
    "classifier_params": {
      "C": 1.0,
      "solver": "lbfgs",
      "max_iter": 1000,
      "random_state": 0
    }
  },
  "2023": {
    "training_n": 2522,
    "scaler_mean": [
      5.334301361081275
    ],
    "scaler_var": [
      12245.572342518502
    ],
    "scaler_scale": [
      110.65971418053863
    ],
    "scaler_n_samples_seen": 2522,
    "classes": [
      0,
      1,
      2
    ],
    "coef": [
      [
        -0.2876084197790753
      ],
      [
        -0.05456694917747007
      ],
      [
        0.34217536895654654
      ]
    ],
    "intercept": [
      0.06165655520638932,
      -0.25743275562046847,
      0.19577620041408156
    ],
    "n_iter": [
      4
    ],
    "convergence_warning": false,
    "classifier_params": {
      "C": 1.0,
      "solver": "lbfgs",
      "max_iter": 1000,
      "random_state": 0
    }
  },
  "2024": {
    "training_n": 2828,
    "scaler_mean": [
      5.359730211361919
    ],
    "scaler_var": [
      12117.66194250837
    ],
    "scaler_scale": [
      110.08025228217988
    ],
    "scaler_n_samples_seen": 2828,
    "classes": [
      0,
      1,
      2
    ],
    "coef": [
      [
        -0.2905000034072302
      ],
      [
        -0.03475799457006117
      ],
      [
        0.325257997977291
      ]
    ],
    "intercept": [
      0.05051088108839364,
      -0.25360189119116006,
      0.2030910101027698
    ],
    "n_iter": [
      4
    ],
    "convergence_warning": false,
    "classifier_params": {
      "C": 1.0,
      "solver": "lbfgs",
      "max_iter": 1000,
      "random_state": 0
    }
  }
}
~~~

### ST2

~~~json
{
  "2020": {
    "training_n": 1530,
    "scaler_mean": [
      6.741732047548031
    ],
    "scaler_var": [
      14949.174171678362
    ],
    "scaler_scale": [
      122.26681549659483
    ],
    "scaler_n_samples_seen": 1530,
    "classes": [
      0,
      1,
      2
    ],
    "coef": [
      [
        -0.29612538225381785
      ],
      [
        0.011732470095044726
      ],
      [
        0.2843929121587725
      ]
    ],
    "intercept": [
      0.09107080951029489,
      -0.29846448389055097,
      0.2073936743802627
    ],
    "n_iter": [
      4
    ],
    "convergence_warning": false,
    "classifier_params": {
      "C": 1.0,
      "solver": "lbfgs",
      "max_iter": 1000,
      "random_state": 0
    }
  },
  "2021": {
    "training_n": 1836,
    "scaler_mean": [
      6.960079714497905
    ],
    "scaler_var": [
      16385.119668624568
    ],
    "scaler_scale": [
      128.00437363084345
    ],
    "scaler_n_samples_seen": 1836,
    "classes": [
      0,
      1,
      2
    ],
    "coef": [
      [
        -0.3014712279288759
      ],
      [
        -0.012473574609075251
      ],
      [
        0.31394480253795015
      ]
    ],
    "intercept": [
      0.1068718107743154,
      -0.30364765043430025,
      0.19677583965997708
    ],
    "n_iter": [
      4
    ],
    "convergence_warning": false,
    "classifier_params": {
      "C": 1.0,
      "solver": "lbfgs",
      "max_iter": 1000,
      "random_state": 0
    }
  },
  "2022": {
    "training_n": 2216,
    "scaler_mean": [
      6.527175825743251
    ],
    "scaler_var": [
      18293.15682128308
    ],
    "scaler_scale": [
      135.25219710334866
    ],
    "scaler_n_samples_seen": 2216,
    "classes": [
      0,
      1,
      2
    ],
    "coef": [
      [
        -0.3163578250948295
      ],
      [
        -0.024539330499317884
      ],
      [
        0.3408971555941482
      ]
    ],
    "intercept": [
      0.08759713196640516,
      -0.29033577156742185,
      0.202738639601026
    ],
    "n_iter": [
      4
    ],
    "convergence_warning": false,
    "classifier_params": {
      "C": 1.0,
      "solver": "lbfgs",
      "max_iter": 1000,
      "random_state": 0
    }
  },
  "2023": {
    "training_n": 2522,
    "scaler_mean": [
      6.005637655219226
    ],
    "scaler_var": [
      18356.617662986588
    ],
    "scaler_scale": [
      135.48659587939534
    ],
    "scaler_n_samples_seen": 2522,
    "classes": [
      0,
      1,
      2
    ],
    "coef": [
      [
        -0.2932741586244155
      ],
      [
        -0.04628254292240764
      ],
      [
        0.3395567015468215
      ]
    ],
    "intercept": [
      0.060315951691594934,
      -0.2567072106297883,
      0.19639125893819573
    ],
    "n_iter": [
      4
    ],
    "convergence_warning": false,
    "classifier_params": {
      "C": 1.0,
      "solver": "lbfgs",
      "max_iter": 1000,
      "random_state": 0
    }
  },
  "2024": {
    "training_n": 2828,
    "scaler_mean": [
      5.956344992548275
    ],
    "scaler_var": [
      18375.203675249995
    ],
    "scaler_scale": [
      135.55516838265515
    ],
    "scaler_n_samples_seen": 2828,
    "classes": [
      0,
      1,
      2
    ],
    "coef": [
      [
        -0.2978124547076395
      ],
      [
        -0.024968963607267747
      ],
      [
        0.32278141831490675
      ]
    ],
    "intercept": [
      0.04895005726752232,
      -0.25275631663743775,
      0.2038062593699188
    ],
    "n_iter": [
      4
    ],
    "convergence_warning": false,
    "classifier_params": {
      "C": 1.0,
      "solver": "lbfgs",
      "max_iter": 1000,
      "random_state": 0
    }
  }
}
~~~

### ST3

~~~json
{
  "2020": {
    "training_n": 1530,
    "scaler_mean": [
      6.660253309148635
    ],
    "scaler_var": [
      11502.366489212649
    ],
    "scaler_scale": [
      107.2490861929026
    ],
    "scaler_n_samples_seen": 1530,
    "classes": [
      0,
      1,
      2
    ],
    "coef": [
      [
        -0.29494384760048287
      ],
      [
        0.0016233000514025214
      ],
      [
        0.29332054754907944
      ]
    ],
    "intercept": [
      0.09177825399432246,
      -0.29785209307022215,
      0.20607383907590637
    ],
    "n_iter": [
      4
    ],
    "convergence_warning": false,
    "classifier_params": {
      "C": 1.0,
      "solver": "lbfgs",
      "max_iter": 1000,
      "random_state": 0
    }
  },
  "2021": {
    "training_n": 1836,
    "scaler_mean": [
      6.942170567763583
    ],
    "scaler_var": [
      12684.90132642954
    ],
    "scaler_scale": [
      112.6272672421272
    ],
    "scaler_n_samples_seen": 1836,
    "classes": [
      0,
      1,
      2
    ],
    "coef": [
      [
        -0.29680390660972295
      ],
      [
        -0.023706506043004016
      ],
      [
        0.3205104126527272
      ]
    ],
    "intercept": [
      0.10815919470697218,
      -0.30378001357630424,
      0.1956208188693237
    ],
    "n_iter": [
      4
    ],
    "convergence_warning": false,
    "classifier_params": {
      "C": 1.0,
      "solver": "lbfgs",
      "max_iter": 1000,
      "random_state": 0
    }
  },
  "2022": {
    "training_n": 2216,
    "scaler_mean": [
      6.435920475467452
    ],
    "scaler_var": [
      13944.447555658424
    ],
    "scaler_scale": [
      118.08661039956404
    ],
    "scaler_n_samples_seen": 2216,
    "classes": [
      0,
      1,
      2
    ],
    "coef": [
      [
        -0.3101557541342437
      ],
      [
        -0.041476285397086844
      ],
      [
        0.35163203953133026
      ]
    ],
    "intercept": [
      0.08960929084852036,
      -0.29053119372395547,
      0.20092190287544465
    ],
    "n_iter": [
      4
    ],
    "convergence_warning": false,
    "classifier_params": {
      "C": 1.0,
      "solver": "lbfgs",
      "max_iter": 1000,
      "random_state": 0
    }
  },
  "2023": {
    "training_n": 2522,
    "scaler_mean": [
      5.943349360375123
    ],
    "scaler_var": [
      13733.108128173586
    ],
    "scaler_scale": [
      117.18834467716312
    ],
    "scaler_n_samples_seen": 2522,
    "classes": [
      0,
      1,
      2
    ],
    "coef": [
      [
        -0.2866587808557077
      ],
      [
        -0.05909100322746324
      ],
      [
        0.34574978408317114
      ]
    ],
    "intercept": [
      0.06213877192022549,
      -0.2574261181753622,
      0.19528734625513897
    ],
    "n_iter": [
      4
    ],
    "convergence_warning": false,
    "classifier_params": {
      "C": 1.0,
      "solver": "lbfgs",
      "max_iter": 1000,
      "random_state": 0
    }
  },
  "2024": {
    "training_n": 2828,
    "scaler_mean": [
      5.9674917010779716
    ],
    "scaler_var": [
      13569.932153433632
    ],
    "scaler_scale": [
      116.49005173590417
    ],
    "scaler_n_samples_seen": 2828,
    "classes": [
      0,
      1,
      2
    ],
    "coef": [
      [
        -0.28945154777101906
      ],
      [
        -0.039576555936093036
      ],
      [
        0.3290281037071111
      ]
    ],
    "intercept": [
      0.050990424969044594,
      -0.25354685672465815,
      0.2025564317556167
    ],
    "n_iter": [
      4
    ],
    "convergence_warning": false,
    "classifier_params": {
      "C": 1.0,
      "solver": "lbfgs",
      "max_iter": 1000,
      "random_state": 0
    }
  }
}
~~~

## Metrics and matched deltas

| Candidate | Year | n | Accuracy | Log Loss | Brier | Delta Accuracy | Delta LL | Delta Brier |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ST0 | 2020 | 306 | 0.5065359477124183 | 1.023119734659012 | 0.6117572218710644 | 0.0 | 0.0 | 0.0 |
| ST0 | 2021 | 380 | 0.5078947368421053 | 1.0253437210487792 | 0.6149829138674616 | 0.0 | 0.0 | 0.0 |
| ST0 | 2022 | 306 | 0.4019607843137255 | 1.0940186385371449 | 0.6610224339161608 | 0.0 | 0.0 | 0.0 |
| ST0 | 2023 | 306 | 0.46078431372549017 | 1.0604285568595655 | 0.638530529273072 | 0.0 | 0.0 | 0.0 |
| ST0 | 2024 | 380 | 0.45 | 1.079241181120235 | 0.6531695943664019 | 0.0 | 0.0 | 0.0 |
| ST0 | pooled | 1678 | 0.466626936829559 | 1.056065401323764 | 0.6357323419292724 | 0.0 | 0.0 | 0.0 |
| ST1 | 2020 | 306 | 0.5065359477124183 | 1.025521467931688 | 0.613276327028039 | 0.0 | 0.00240173327267601 | 0.0015191051569746206 |
| ST1 | 2021 | 380 | 0.5026315789473684 | 1.0220785316152827 | 0.6128025164667414 | -0.0052631578947368585 | -0.003265189433496518 | -0.00218039740072018 |
| ST1 | 2022 | 306 | 0.3954248366013072 | 1.0967815963642358 | 0.663286640100497 | -0.006535947712418333 | 0.002762957827090906 | 0.002264206184336204 |
| ST1 | 2023 | 306 | 0.46405228758169936 | 1.0619452020662101 | 0.6396446132090662 | 0.0032679738562091942 | 0.001516645206644629 | 0.0011140839359942145 |
| ST1 | 2024 | 380 | 0.43157894736842106 | 1.07954054290429 | 0.6534484491597772 | -0.01842105263157895 | 0.0002993617840549856 | 0.00027885479337530494 |
| ST1 | pooled | 1678 | 0.4606674612634088 | 1.0566121679524736 | 0.6361948072237088 | -0.00595947556615023 | 0.0005467666287095607 | 0.0004624652944363872 |
| ST2 | 2020 | 306 | 0.5196078431372549 | 1.021242952739507 | 0.610605337141693 | 0.013071895424836666 | -0.0018767819195049107 | -0.001151884729371444 |
| ST2 | 2021 | 380 | 0.5105263157894737 | 1.0231617683622922 | 0.6135203862899687 | 0.0026315789473684292 | -0.002181952686487021 | -0.001462527577492878 |
| ST2 | 2022 | 306 | 0.40522875816993464 | 1.0948055295204087 | 0.6616125917169673 | 0.0032679738562091387 | 0.0007868909832637883 | 0.0005901578008065123 |
| ST2 | 2023 | 306 | 0.4673202614379085 | 1.0601424382481306 | 0.6383659978613666 | 0.006535947712418333 | -0.0002861186114349046 | -0.0001645314117053598 |
| ST2 | 2024 | 380 | 0.4473684210526316 | 1.0789056697991928 | 0.6529784470263815 | -0.0026315789473684292 | -0.00033551132104214787 | -0.00019114734002034783 |
| ST2 | pooled | 1678 | 0.47079856972586415 | 1.055244367209074 | 0.6352254101528853 | 0.004171632896305122 | -0.0008210341146899225 | -0.000506931776387165 |
| ST3 | 2020 | 306 | 0.5098039215686274 | 1.023532239538456 | 0.6121536953024953 | 0.0032679738562091387 | 0.00041250487944410885 | 0.0003964734314308993 |
| ST3 | 2021 | 380 | 0.5105263157894737 | 1.0205314526832683 | 0.6117956175071595 | 0.0026315789473684292 | -0.004812268365510963 | -0.0031872963603021276 |
| ST3 | 2022 | 306 | 0.39869281045751637 | 1.0974002323430736 | 0.6637498614364064 | -0.0032679738562091387 | 0.0033815938059287287 | 0.0027274275202455733 |
| ST3 | 2023 | 306 | 0.477124183006536 | 1.0617460706667803 | 0.6395630380203744 | 0.016339869281045805 | 0.0013175138072147874 | 0.0010325087473024297 |
| ST3 | 2024 | 380 | 0.4263157894736842 | 1.07932923072334 | 0.653327478151038 | -0.023684210526315808 | 8.804960310504484e-05 | 0.00015788378463610364 |
| ST3 | pooled | 1678 | 0.464839094159714 | 1.0559277078154314 | 0.6358042636152881 | -0.0017878426698450522 | -0.00013769350833259253 | 7.192168601566351e-05 |

## Exactly two transition views (context ONLY)

| Candidate | Year | View | n | Log Loss | Brier |
| --- | --- | --- | --- | --- | --- |
| ST0 | 2020 | opening | 45 | 1.0277013500883585 | 0.6175102361637791 |
| ST0 | 2020 | any_team_first5 | 45 | 1.0277013500883585 | 0.6175102361637791 |
| ST0 | 2021 | opening | 50 | 0.9564829897368693 | 0.5617085879037228 |
| ST0 | 2021 | any_team_first5 | 55 | 0.9768727965198795 | 0.577377590670173 |
| ST0 | 2022 | opening | 45 | 1.112768297390112 | 0.6729966704279403 |
| ST0 | 2022 | any_team_first5 | 50 | 1.0928566875795793 | 0.6597054438087785 |
| ST0 | 2023 | opening | 45 | 1.0807970435080223 | 0.6527238866156764 |
| ST0 | 2023 | any_team_first5 | 45 | 1.0807970435080223 | 0.6527238866156764 |
| ST0 | 2024 | opening | 50 | 1.0713173847657194 | 0.6450773423040043 |
| ST0 | 2024 | any_team_first5 | 51 | 1.0945069804297334 | 0.6610334476895184 |
| ST0 | pooled | opening | 235 | 1.0482851907213686 | 0.6288709881051879 |
| ST0 | pooled | any_team_first5 | 246 | 1.053142771956609 | 0.6325783781891845 |
| ST1 | 2020 | opening | 45 | 1.0266882247157008 | 0.6168250356607988 |
| ST1 | 2020 | any_team_first5 | 45 | 1.0266882247157008 | 0.6168250356607988 |
| ST1 | 2021 | opening | 50 | 0.9547371874859639 | 0.5617630993078934 |
| ST1 | 2021 | any_team_first5 | 55 | 0.9722225287304176 | 0.5741533140677052 |
| ST1 | 2022 | opening | 45 | 1.1219912558644525 | 0.6783597143088121 |
| ST1 | 2022 | any_team_first5 | 50 | 1.1013723289347737 | 0.6647799693263953 |
| ST1 | 2023 | opening | 45 | 1.0743558181502026 | 0.6483212554392507 |
| ST1 | 2023 | any_team_first5 | 45 | 1.0743558181502026 | 0.6483212554392507 |
| ST1 | 2024 | opening | 50 | 1.0712890129479729 | 0.6459001235748871 |
| ST1 | 2024 | any_team_first5 | 51 | 1.0938371407836833 | 0.6613778761843163 |
| ST1 | pooled | opening | 235 | 1.0482463764449486 | 0.6291103463299481 |
| ST1 | pooled | any_team_first5 | 246 | 1.0523314294140047 | 0.6320296159550647 |
| ST2 | 2020 | opening | 45 | 1.0200844635470439 | 0.6122451788332632 |
| ST2 | 2020 | any_team_first5 | 45 | 1.0200844635470439 | 0.6122451788332632 |
| ST2 | 2021 | opening | 50 | 0.9477137210946351 | 0.5556556728192118 |
| ST2 | 2021 | any_team_first5 | 55 | 0.9659095116087021 | 0.5693336297877203 |
| ST2 | 2022 | opening | 45 | 1.1161305511206703 | 0.675560504193443 |
| ST2 | 2022 | any_team_first5 | 50 | 1.0981375407532554 | 0.6636652690836686 |
| ST2 | 2023 | opening | 45 | 1.0830162999761253 | 0.6546339801060288 |
| ST2 | 2023 | any_team_first5 | 45 | 1.0830162999761253 | 0.6546339801060288 |
| ST2 | 2024 | opening | 50 | 1.0752142279097858 | 0.6478565900701087 |
| ST2 | 2024 | any_team_first5 | 51 | 1.0979410774612484 | 0.6635469990449432 |
| ST2 | pooled | opening | 235 | 1.0468587515284844 | 0.6280229701508047 |
| ST2 | pooled | any_team_first5 | 246 | 1.0514895507528765 | 0.6314921633986516 |
| ST3 | 2020 | opening | 45 | 1.018848990676199 | 0.6112895229995727 |
| ST3 | 2020 | any_team_first5 | 45 | 1.018848990676199 | 0.6112895229995727 |
| ST3 | 2021 | opening | 50 | 0.946608448107383 | 0.5558715247224006 |
| ST3 | 2021 | any_team_first5 | 55 | 0.9628869430868092 | 0.5671482561238311 |
| ST3 | 2022 | opening | 45 | 1.125761606437679 | 0.681143074364923 |
| ST3 | 2022 | any_team_first5 | 50 | 1.106245803419027 | 0.6683908236741993 |
| ST3 | 2023 | opening | 45 | 1.0776862728011438 | 0.6509058937980461 |
| ST3 | 2023 | any_team_first5 | 45 | 1.0776862728011438 | 0.6509058937980461 |
| ST3 | 2024 | opening | 50 | 1.075951604651992 | 0.6490698195999813 |
| ST3 | 2024 | any_team_first5 | 51 | 1.097973390543477 | 0.6642146010293921 |
| ST3 | pooled | opening | 235 | 1.0473674969538074 | 0.6284991460358871 |
| ST3 | pooled | any_team_first5 | 246 | 1.0512674870525351 | 0.631245665361433 |

## Candidate gate and selection

| Candidate | Improved LL folds /5 | Pooled LL improved | >=3 folds | Pooled Brier nonworse | Pass |
| --- | --- | --- | --- | --- | --- |
| ST1 | 1/5 | False | False | False | False |
| ST2 | 4/5 | True | True | True | True |
| ST3 | 1/5 | True | False | False | False |

Selected candidate: ST2
Minimum-anchored tied set: ['ST2']
Tie: absolute1e-12/rtol0 from minimum passing pooled LL; mechanisms ST1=1/ST2=1/ST3=2; then ST1/ST2/ST3.

## Interpretation and actions not performed

Accuracy/context excluded from gates and selection; no causality/unseen-improvement claim.
Closed calibration lane remains unchanged. No calibration/architecture/P/G/workload/xG/player/suspension evaluation.
ST0 refit/replay/prediction / OOF regeneration / diagnose(): NOT RUN.
2025 / 2026+ / lockbox inspection / HTTP / production prediction / activation: NOT USED.
Feature-contract changes=NO; parameter-contract changes=NO; tuning=NOT RUN; adaptive follow-up=NOT RUN.
Saved Champion A/persisted/opened predictions: UNCHANGED. Derived datasets/models/plots: NOT CREATED. Push NOT PERFORMED.
A pass permits ONLY a separate prospective freeze at a NEW unseen boundary, not promotion.

## Final research decision

PROCEED_TO_SEASON_TRANSITION_PROSPECTIVE_FREEZE
