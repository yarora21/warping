# PR 5 — Rule authoring and end-to-end demo

Run `make up` and open http://localhost:5180. No new migration or seed reset is required. Existing human changes are preserved. A fresh installation needs `make seed`; the instructions below assume its default demo date, September 12, 2026. Saves deliberately change the demo company. Scheduled corrections/cancellations remain out of scope, so preview before saving.

## Create a policy and rule

1. Open **Policies**, choose **Application access**, and leave the effective date at September 12. Click **Create policy**. Name it `Notion`, enter a description and reason, and save. Nobody gets it just from creating the policy.
2. Click **Add rule**, name it `Notion for Engineering`, select Notion, and add a condition: **Department / is / Engineering**. Enter a reason and preview.
3. Review the employees who gain Notion, including future transitions. Save. In Assignments, select Jamie and filter for Notion to verify the result and “Why?” explanation. Manual exclusions still win.
4. Edit this rule to **Department / is / Sales** and preview. Jamie and other former matches lose Notion; Sales gains it. Save and verify both groups in the report. This demonstrates removal as well as addition during reconciliation.
5. Use **End rule**, preview, and save. It stops assigning Notion from the selected date; the policy remains in the catalog. Ending a rule does not delete its historical evidence.

## Arrange pay rules without numbers

1. Choose **Pay schedule** and October 1 as the effective date. Move Default monthly pay above US employee pay.
2. Enter a reason and preview the order change. US employees ordinarily switch to monthly pay; explicit manual pay assignments remain unchanged and are listed separately.
3. Save. In Assignments, September 30 retains the old result and October 1 uses the new order. “Why?” names the selected rule and explains why another match was not used.
4. Trying to rewrite this scheduled ordering before October 1 should show a clear scheduled-version error. Do not expect cancellation or historical correction controls.

## Guardrails and dates

- Before saving the reorder above, preview ending Default monthly pay. International employees would lose required coverage, so the preview lists gaps and offers no save button. Cancel.
- Create a policy with an October 1 start. It is available in the rule editor when October 1 is selected, not before. New policy creation does not change the current-date catalog until its start date.
- Select **Member of any group / is any of / Launch team** to exercise ID-backed membership rules. Use **Completed months of service / is at least / 24** for tenure. All conditions in a rule must match.
- Change inputs in a second tab after previewing, then save. The service revalidates and shows the actual saved impact (or blocks the save if required coverage is no longer valid).

## Full take-home demo

1. Browse People/Policies to show seeded setup and cardinality labels.
2. Query Jamie and Priya together on a chosen date; explain their differing pay schedules.
3. Query Morgan before/after September 30, 2026 to demonstrate the tenure transition without a daily job.
4. Add a temporary manual pay assignment and show its expiration back to automatic rules.
5. Edit employee location/group/manager information using the PR 4 walkthrough; preview and save downstream assignment changes.
6. Add a new employee, checking assignments before completing onboarding.
7. Create/edit a rule and show both newly matching and formerly matching employees in the preview.
8. Show dated timelines and “Why?”; explain that source revisions and change snapshots are stored even though a full audit-history screen is deferred.

## Verification

47 backend tests cover the core domain/database behavior. PR 5 adds focused tests for policy creation, rule edits/end, former matches, historical reordering, scheduled conflicts, coverage rejection, rollback, validation, future policy availability, deduplication, and preserved manual exceptions. Generated API types, TypeScript, formatting, and the production build pass. Browser interactions and visual/keyboard checks belong to the human; none are automated.

PR 5 remains local until explicitly requested to push. Nothing has been emailed to the take-home submission address.
