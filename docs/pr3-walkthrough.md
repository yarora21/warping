# PR 3 — Human walkthrough

Run `make up` to apply migration 0003 and refresh the app at http://localhost:5180. Existing employee/rule data and assignments are preserved. For a fresh database, also run `make seed`. The default demo date is September 12, 2026. PR 3 is pushed on `feat/pr3-manual-overrides`.

1. Open Jamie Park and choose **Change assignment** in Manual exceptions. Select Pay schedule → Monthly pay, effective September 12, ending October 1 (exclusive). Enter a reason.
2. Preview the change. The before/after view should show Monthly pay during the exception and Biweekly resuming October 1. Preview alone must not change the profile/report.
3. Save. Inspect the Manual badge, “Why?” attribution/reason, and timeline. The Assignments report should agree with the profile. Select September 30 and October 1 to check the expiration boundary.
4. Create an Application access → Exclude policy → GitHub exception. GitHub disappears, while Slack and Figma remain. The exclusion stays visible in Manual exceptions. Run `make reconcile`; the exclusion must remain effective.
5. Use **Use automatic assignment** on the exclusion, provide a reason, preview, and save. GitHub returns because the Engineering rule still matches.
6. Add an app manually to an employee who does not get it automatically—for example GitHub for Oliver James. Inspect the manual explanation and optional expiration.
7. For optional Sick leave, choose **Leave unassigned**. The explicit clear is visible. Required Pay schedule does not offer that action.
8. Replace Jamie's active monthly exception with a different pay choice/date. Verify earlier dated assignments and reasons remain explainable. Ending the replacement resumes the current rules, not the earlier manual choice.
9. Try an empty reason, an end date before the start, or an effective date outside employment. Inspect validation messages and verify invalid saves do not partially change assignments.
10. Review the forms, expanded explanations, date labels, and narrow-window/keyboard behavior manually. The server revalidates saves; if inputs change after preview, the actual saved result is displayed and flagged.

## Verification

33 backend cases pass, including all four override actions, expiration, preview without persistence, save/preview agreement, return to automatic rules, overlap rejection, rollback, and exclusions surviving reconciliation. Tests use an isolated temporary schema and preserve your demo edits. API types and the frontend build pass. No computer-use/browser tests were added.

Ending/creating an override is limited to today or future dates within an employment. Historical correction/cancellation editors, employee onboarding/edits, and rule editing remain later work. A future scheduled conflict produces a clear error rather than silently replacing that schedule.
