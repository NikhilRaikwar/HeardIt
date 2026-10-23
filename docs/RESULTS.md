# HeardIt results template

Use this worksheet to record an actual experiment run. Leave fields blank until values have been observed; do not fill it with demo or illustrative data.

| Run date | Test ID | Published tests | Total responses | Audio responses | Audio intended-label rate (Wilson 95% CI) | Text responses | Text intended-label rate (Wilson 95% CI) | Observed voice lift |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |

## Method

Participants are assigned by the server to an audio or text condition. The reported success rate is the share of submitted responses selecting the creator's intended label. Wilson 95% intervals are computed for each condition. Voice lift is the audio group's observed rate minus the text group's observed rate in this randomized sample; it is exploratory and does not establish universal voice quality or statistical significance by itself. Treat small samples as preliminary and groups with no responses as insufficient data.

## Export from `/admin`

Open `/admin` and authenticate with the configured admin key. Record the clearly labelled **server-confirmed** published-test and accepted-vote totals separately from the **client-reported** funnel. These aggregate admin metrics are not a test-level results export and the page has no CSV download. For one experiment's answer distributions, sample sizes, intervals, and voice lift, open its private `/r/[id]` results page and copy the displayed values into the table above. Do not use client-reported funnel counts as vote totals.
