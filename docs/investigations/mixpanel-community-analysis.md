# GitHub community analysis in Mixpanel

## Question and conclusion

Does a change in event volume imply a similar change in participation?

In the approved 500-repository snapshot, events fell **25.91%** between the last two
complete weeks, while distinct contributor accounts fell **1.24%**. PR/issue events
fell **7.36%**. Volume and participation breadth moved at different rates; event
counts alone would overstate the decline in observed participation. This is a
descriptive finding, not evidence of a cause or of overall community health.

## Dataset and lineage

| Field | Approved value |
| --- | --- |
| Source | Public GH Archive events queried through BigQuery |
| Coverage | `[2026-07-25, 2026-10-23)` UTC; 90 days |
| Selected / observed repositories | 500 / 421 |
| Unique source events | 94,133 |
| Distinct contributor accounts | 27,936 |
| PR/issue-category events | 41,432 |
| Source refresh | 2026-10-24 16:36:22 UTC |
| Release | [community-data-40112298324-1](https://github.com/yash-rai-93/argo-data-platform/releases/tag/community-data-40112298324-1) |
| Scope registry | [config/repository-scope-v1.json](../../config/repository-scope-v1.json) |
| Snapshot import label | `gharchive_500_2026-07-25_2026-10-23` |
| Mixpanel event | `github_contribution_expanded` |
| Checkpoint audit event | `github_checkpoint_validated_expanded` |

Source-state SHA-256:

    10f08f40f82bc0541d4a100b04c94cb23d829ba182e238515503164d896dff43

Scope SHA-256:

    cff1114655b4b2fafe17c09fbd52268635b7482b5f10fa1d56cde3df578c1e4a

The [approved pointer](../../data/community-source.json) pins the summary checksum;
the summary pins the compressed event-state checksum. The publisher verifies all
13 backfill manifests and recomputes the full-range aggregates before publication.
See [publication and rollback](../COMMUNITY_PUBLICATION.md).

## Reports delivered

[Open the Mixpanel index](https://mixpanel.com/project/4028794/app/boards#id=11608511).
Project access is required; the [public ARGO report](https://argo-data-platform.vercel.app/community)
provides the same source with coordinated date/repository/category exploration.

| Board | Analyses |
| --- | --- |
| [Community Overview](https://mixpanel.com/project/4028794/app/boards#id=11608513) | Verified totals, exact UTC daily counts, repository participation and weekly category drivers |
| [Participation & Concentration](https://mixpanel.com/project/4028794/app/boards#id=11608514) | Returning/joining/absent accounts, top-account shares and observed cohort returns |
| [Data Trust & Pipeline Health](https://mixpanel.com/project/4028794/app/boards#id=11608515) | Covered versus expected days, validation, duplicate IDs, source metadata and query bytes versus cap |

Five native reports are embedded: two overview reports and three participation
reports. Other analyses use interactive native query links because the project
reached its saved-report allowance. Static findings are explicitly dated snapshot
notes; changing a report filter does not recalculate those notes.

### Finding 1: activity declined more than participation

| Metric | Oct 9–15 UTC | Oct 16–22 UTC | Absolute change | Relative change |
| --- | ---: | ---: | ---: | ---: |
| Events | 5,411 | 4,009 | −1,402 | −25.91% |
| Distinct accounts | 1,698 | 1,677 | −21 | −1.24% |
| PR/issue-category events | 1,521 | 1,409 | −112 | −7.36% |

Both periods contain seven covered UTC days and use the same repository scope.
PR/issue events count source events in those categories, not unique or merged PRs.
Distinct counts are not additive across days, categories or repositories.

### Finding 2: stable totals can hide changing membership

- **351 returning:** present in both weeks.
- **1,326 joining:** present in Oct 16–22, absent in Oct 9–15.
- **1,347 absent:** present in Oct 9–15, absent in Oct 16–22.

Reconciliation: `351 + 1,326 = 1,677` current accounts and
`351 + 1,347 = 1,698` prior accounts.

Joining does not mean new to GitHub or open source. Absence is an observation
within this scope and period, not churn or an explanation of a person's intentions.

### Finding 3: quantify concentration alongside volume

Across the full 90-day snapshot, the largest account supplied **3.41%** of events;
the top five supplied **14.99%**. Accounts can participate in several repositories.
These shares measure source-account concentration, not the number of humans,
automation, contribution quality or community health.

The Mixpanel rank and overlap properties were computed for the fixed snapshot
before report filters. A filter narrows those accounts' events without reranking
or redefining membership. Use ARGO's community report to recompute these measures
under a changed repository/category scope.

### Finding 4: source coverage and validity need separate evidence

The published backfill records **90 / 90 covered days**, zero retained duplicate
IDs and zero recorded validation failures. Thirteen extracts were checked before
promotion. Successful queries of expected daily tables verify query coverage;
they do not guarantee complete capture of every GitHub event.

| BigQuery usage | Bytes |
| --- | ---: |
| Processed | 15,532,379,573 |
| Billed/accounted | 15,537,799,168 |
| Configured backfill cap | 20,000,000,000 |

This is backfill usage evidence, not currency spending or an account-wide budget.
The snapshot contains one latest refresh record, so the boards do not invent
pipeline success-rate history or incremental new-ID reconciliation.

## Import and reconciliation

The import preserved original event timestamps, source event IDs and public
repository fields. Historical contributor identities use `github:` plus
a deterministic SHA-256 of the source handle, distinct from anonymous website
visitor identities. Hashing public handles does not make the dataset anonymous.

Contributor insert IDs are deterministic over the expanded import label and event
ID. The separate checkpoint audit event has its own deterministic ID. No People
profiles, visitor identity merges, model-training records or synthetic Kafka
benchmark fixtures were added.

The completed import accepted **94,134 records in 48 batches**: 94,133 contributor
events plus one checkpoint audit event. Native Mixpanel queries reconciled
**94,133 events, 27,936 accounts and 41,432 PR/issue events**, along with the overlap
and concentration findings above. Counting both event names together would add
the audit event and produce the wrong activity total.

Queries isolate `source_snapshot = gharchive_500_2026-07-25_2026-10-23` and
`scope = argo_500_repositories`. They exclude the earlier import and website
events. Exact daily tables use `source_day_label` for UTC boundaries;
ordinary Mixpanel date trends follow the project timezone. Query date ranges
include a boundary buffer, with snapshot filters fixing the source population.

For cohort reports, assignment uses the first observed week within this snapshot,
not lifetime GitHub participation. Only complete seven-day source weeks are
compared; the final six-day period is partial. Unobservable future/partial cells
remain absent rather than zero. Neither daily unique counts nor cohort cells
should be summed to estimate full-range distinct accounts.

## Earlier concentration investigation

The archived 24-repository study covers September 24–October 21, 2026 UTC:
**5,657 events and 1,116 accounts**. Its final-week events fell **34.62%** while
PR/issue events rose **4%**.

On October 14, it observed 457 events / 92 accounts; the largest account supplied
256 events (**56.02%**). On October 21, it observed 382 events / 72 accounts;
the largest account supplied 242 (**63.35%**). These spikes support a concentration
interpretation within that earlier scope without proving automation.

See the [published investigation and reproduction steps](activity-concentration.md).
Its findings and Mixpanel queries remain under labelled archive sections. Expanding
from 24 to 500 repositories is a scope change, not evidence of organic growth.

## Reproduce and extend

1. Read the dated release above and validate the compressed-state SHA-256.
2. Count unique event IDs and distinct handles from `events`; apply the
   documented category mapping for PR/issue counts.
3. Select the two exact UTC weeks and compute account sets and their intersection
   and differences. Recompute rather than summing per-day unique counts.
4. In Mixpanel, select `github_contribution_expanded` and the exact snapshot/scope
   properties. Compare totals with this document and the pinned release.
5. For the next snapshot, run ARGO's reviewed incremental publication first, then
   perform a separately reconciled import. Existing boards are not an automatic sync.

The 2023 historical model study remains separate. This analysis does not validate
the historical model on current contributors or trigger retraining.
