v13.25 SMART BACKFILL

Fixes both problems seen in Backfill Movie Metadata #8.

1. Efficient queue:
- removes generic Season/Episode placeholders before TMDb;
- removes "programme unavailable" placeholders;
- skips Ukrainian titles before HTTP lookup;
- strips generated "(YEAR) · IMDb X.X" decoration;
- merges duplicate normalized works after cleanup;
- disables expensive multi-fallback for nightly backfill;
- lowers empty-plan fallback limit from 4 to 2.

2. Reliable publish:
- commits durable DB/report files;
- stashes all other runtime changes;
- then rebases and pushes.

Install over repo root -> Commit.
Then run Backfill Movie Metadata manually with budget 5000 once.

Success marker:
Metadata backfill published successfully

No Worker deploy required.
No Update EPG required for this patch.
