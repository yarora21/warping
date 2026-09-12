# PR 1 — Human walkthrough

## Start

Run `make up` and `make seed`, then visit http://localhost:5180. Keep the default demo clock at **September 12, 2026** for this walkthrough. All information is fictional.

## What to inspect

1. The People screen shows 18 people, including one upcoming hire and one former employee. The header shows the demo date.
2. Search for **Jamie** and open Jamie Park. Verify Engineering, New York, salaried employment, Alex Chen as manager, and Launch team membership.
3. Click Alex's name to inspect their profile, then return to the directory. Filter to Engineering; clear filters and try a search with no results.
4. Open **Morgan Ellis** and note the October 2024 start date. PR 2 will demonstrate the upcoming two-year tenure threshold.
5. Inspect **Riley Davis**, who starts September 26, 2026, and **Ben Wilson**, whose employment ended before the demo date. Their statuses should be clear.
6. Open Policies. Explore 11 policies across five categories. Pay schedule and Vacation say “Choose one,” Sick leave says “Optional,” and Apps/Training say “Multiple allowed.” Catalog status must not imply that any employee has been assigned a policy yet.
7. Inspect narrow-window layouts and keyboard navigation manually. Check focus states, labels, search, and manager links.
8. Run `make seed` again and refresh. Counts should not grow. Run `make down`, then `make up`; data should still be present.

## Intentionally not in this increment

No assignment resolver, rule editor, report, manual override, onboarding form, or employee editing yet. The profile explicitly identifies assignments as the next increment. There are no inert edit buttons or simulated assignment results.

## Automated checks

Run `make test` for additive seeds, readable directory/catalog, foreign keys, interval overlap rejection, and immutable revision behavior. Tests use transactions that roll back. Run `make check` after `npm ci` in `frontend` for type checking and the production build. UI testing is yours; no browser automation is included.

Implementation verification: four database checks passed; API type generation, TypeScript checking, and the production frontend build passed. The API returned 18 people, five categories, and 11 policies. Manual visual review remains for the human.
