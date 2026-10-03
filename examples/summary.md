# Example runs (deepseek/deepseek-v4.1-flash)

Average: 4387 tokens, 39.3 s per case.

| example | exit | seconds | tokens (prompt+completion) | requests | repairs | checks pass | theme | paper figure |
|---|---|---|---|---|---|---|---|---|
| [dropout](dropout/out/index.html) | 0 | 39.7 | 6061 (2984+3077) | 2 | 1 | True | network/technical | 2 figure(s) |
| [pagerank](pagerank/out/index.html) | 0 | 39.5 | 3592 (1595+1997) | 1 | 0 | True | network/technical | 0 figure(s) |
| [sampling](sampling/out/index.html) | 0 | 38.6 | 3508 (1511+1997) | 1 | 0 | True | wave/classic | 0 figure(s) |
