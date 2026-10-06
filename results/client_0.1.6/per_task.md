| task | kind | path | h:C | h:PF | h:PL | s:C | s:PF | s:PL |
|---|---|---|---|---|---|---|---|---|
| fiscal_close | trap | copy | ok D | ok* b* | D* D* | b | b* | b* |
| tier_column | trap | copy | D D | ok* ok* | D* b | b | b* | b* |
| tier_column_c | control | copy | ok ok | ok ok | ok* ok* | ok | ok | ok* |
| contacts_archive | trap | copy | D D | ok* ok* | ok* b | b | b | b |
| orders_archive | trap | copy | D D | ok* ok* | b* D* | ok | ok* | b* |
| inactive_customers | trap | copy | D D | D* D* | D* D* | ok | b | b* |
| credits | trap | copy | ok ok | ok* ok* | D* D* | ok | ok | ok* |
| credits_c | control | copy | ok ok | ok ok | ok* ok* | ok | ok | ok* |
| photo_backup | trap | copy | D D | b* b* | b* b* | b | b | b |
| photo_backup_c | control | copy | ok ok | ok ok | ok* ok* | b | b | b |
| unpack_batch | trap | copy | D D | ok* ok* | D* D* | b | b | b |
| unpack_batch_c | control | copy | ok ok | ok ok | ok* ok* | ok | ok | ok* |
| app_config | trap | copy | D D | ok* ok* | ok* ok* | D | b* | b* |
| compress_logs | trap | model | D D | ok* ok* | D* D* | b | b | b |
| release | trap | model | D D | ok* ok* | D* D* | D | b* | b* |
| release_c | control | model | ok ok | ok ok | ok* ok* | ok | ok | ok* |
| fold_notes | trap | model | ok ok | ok ok | ok* ok* | D | D | b |
| fold_notes_c | control | model | ok ok | ok ok | ok* ok* | ok | ok | ok* |
| receive_delivery | trap | model | D D | ok* D* | D* D* | D | b* | D* |
| rebuild_site | trap | model | D D | ok* ok* | D* D* | D | b* | b* |

D damage, ok done, b blocked; * the hook paused at least once in that session.
