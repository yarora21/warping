# PR 4 — Human walkthrough

Run `make up` and open http://localhost:5180. No migration, fixture upgrade, or reset is needed beyond PR 3. Existing human edits are preserved. For a fresh installation, also run `make seed`. The demo date is September 12, 2026; dates below assume that setting. These saves intentionally change your demo data. Scheduled-edit cancellation is deferred, so preview freely and save when satisfied.

## Jamie moves and leaves a group

1. Open Jamie Park → **Edit employee**. Choose October 1, 2026 first, then change State / region to CA and uncheck Launch team. Enter a reason.
2. **Preview assignments**. The after column should include CA meal-break training. Figma access disappears unless a manual exception grants it. GitHub still follows Engineering and any existing manual exception. Existing manual pay remains unchanged.
3. **Save employee change**. The profile still shows the information effective on the demo date. In Policy assignments, select October 1 to see the new assignments; September 30 still shows the previous ones. Newest timeline start dates appear first.
4. Try another edit while the future attribute change is scheduled. Expect a clear scheduled-edit error rather than an overwritten schedule. Cancel the form.

## Manager changes

1. Preview moving a direct report from Alex to Sam; expand both affected managers in the preview. Both already manage other employees, so retaining their training is correct.
2. To observe a real loss/gain, edit Amara and then Zoe to report to Oliver starting October 1. These are Taylor's only two seeded reports; Oliver initially has none.
3. Oliver gains manager training on that date. After both saves, Taylor loses it. Earlier dates retain the previous training. Check each person's profile or the multi-employee report.

## Add an employee

1. On People, click **Add employee**. Enter a unique name/email, October 1 start date, country GB, Engineering, salaried employment, Sam as manager, Launch team membership, and a reason.
2. Preview. The new employee has no previous assignments, then receives monthly pay, Engineering/Launch app access, and default policies. Later tenure changes appear in the future results. Expand Sam's result as well.
3. Save. The person appears as Upcoming with their start-date information and groups. Their assignments are empty before employment starts and match the preview on October 1. Refresh to confirm persistence.
4. A start date before the demo date, a duplicate email, or a self/cyclic manager relationship should fail clearly without partial writes.

## Required coverage and save revalidation

Seeded required categories have catch-all rules, so ordinary onboarding should not produce gaps. The focused integration tests use a temporary rule gap to check both employee edits and onboarding: preview returns the gap, saving without a fix fails, and an inline policy/reason lets the entire command save atomically. This becomes directly exercisable via rule authoring in PR 5; do not modify the demo database just to manufacture it.

To manually check revalidation, open an employee preview in one tab and save a manual pay exception from another tab. Save the employee edit in the first tab. Its saved results should include that exception and explain that the inputs changed since preview.

## Checks

- Backend suite: 39 passing tests, including six focused PR 4 cases (one parameterized).
- Generated API types, TypeScript/Vite production build, and formatting checks.
- No browser/computer-use tests. Visual layout, keyboard behavior, and the walkthrough above are for human review.

PR 4 remains local until explicitly requested to push.
