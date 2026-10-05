# Three ideas for the look-when-unsure loop (no training)

Written on 2026-10-04 before any chain of this test ran (criteria fixed in advance).

The release model (V42), served as released, on the 120 chains of the earlier tests (cards 8, the other worlds 4 per
length; 100 and 200 actions), against its own default (chain confidence below 0.9 with checks) on the same chains:

- **check0.9E**: the default, and a look after the last action too when the rule says so (today the loop never looks
  after the last action, so a flagged last-step error stays);
- **adapt0.9E**: the default whose threshold learns from the looks: halfway to 1 after a look that finds the forecast
  wrong, 25% further from 1 after a look that finds it right (between 0.5 and 0.995); plus the last-action look;
- **views0.9E**: the default plus a second view of the state in each family's own wording (containers full/empty,
  lamps and machines "same state" for neighbours, cards "at which position"); a disagreement between the two views
  triggers a look; plus the last-action look. **views0.5E**: the same at threshold 0.5.

A mode improves the loop if, pooled over the four worlds, it has fewer steps wrong along the way without more than 10%
more looks, or fewer looks without more steps wrong; exactness at the end is reported, with the misses at the last
action counted apart.
