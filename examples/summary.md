# Example runs (deepseek/deepseek-v4.1-flash)

Average: 5019 tokens, 26.9 s per case.

| example | exit | seconds | tokens (prompt+completion) | requests | repairs | checks pass | theme | paper figure |
|---|---|---|---|---|---|---|---|---|
| [adam](adam/out/index.html) | 0 | 27.6 | 3672 (1455+2217) | 1 | 0 | True | landscape/modern | - |
| [attention](attention/out/index.html) | 0 | 42.2 | 5026 (2856+2170) | 2 | 1 | True | matrix/technical | - |
| [batchnorm](batchnorm/out/index.html) | 0 | 39.6 | 4505 (2367+2138) | 2 | 1 | True | distribution/modern | - |
| [distillation](distillation/out/index.html) | 0 | 13.4 | 5028 (3075+1953) | 2 | 1 | True | distribution/technical | - |
| [dropout](dropout/out/index.html) | 0 | 33.2 | 9350 (5288+4062) | 3 | 2 | True | network/classic | - |
| [entropy](entropy/out/index.html) | 0 | 11.1 | 3390 (1723+1667) | 1 | 0 | True | distribution/classic | - |
| [klopfenstein](klopfenstein/out/index.html) | 0 | 20.8 | 4986 (2623+2363) | 1 | 0 | True | circuit/classic | - |
| [pagerank](pagerank/out/index.html) | 0 | 12.9 | 3751 (1878+1873) | 1 | 0 | True | network/classic | - |
| [positional](positional/out/index.html) | 0 | 44.0 | 7360 (3833+3527) | 3 | 2 | False | wave/technical | - |
| [sampling](sampling/out/index.html) | 0 | 24.2 | 3123 (1335+1788) | 1 | 0 | True | wave/classic | - |
