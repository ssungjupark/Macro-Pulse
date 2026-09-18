# External scheduler setup

GitHub Actions scheduled events can be delayed. For time-sensitive market-close delivery, use an external HTTP scheduler to dispatch the existing workflow and keep GitHub cron as a fallback.

## Endpoint

POST

https://api.github.com/repos/ssungjupark/Macro-Pulse/actions/workflows/daily_report.yml/dispatches

## Required headers

- Accept: application/vnd.github+json
- Authorization: Bearer <FINE_GRAINED_GITHUB_TOKEN>
- X-GitHub-Api-Version: 2022-11-28
- Content-Type: application/json

Use a fine-grained personal access token scoped only to `ssungjupark/Macro-Pulse` with **Actions: Read and write** permission. Do not commit the token to this repository.

## Korean market close

Preferred schedule:
- Asia/Seoul: Monday-Friday 15:40
- UTC equivalent: Monday-Friday 06:40

Request body:

```json
{
  "ref": "main",
  "inputs": {
    "market": "KR",
    "delivery_guard": "true"
  }
}
```

`delivery_guard=true` makes the external dispatch use the same daily delivery cache as GitHub's built-in scheduled runs. Once the external run sends successfully, delayed GitHub cron fallbacks for the same market/date will restore the cache and skip duplicate delivery.

## U.S. market close

Optional external schedule:
- Asia/Seoul: Tuesday-Saturday 06:30
- UTC equivalent: Monday-Friday 21:30

Request body:

```json
{
  "ref": "main",
  "inputs": {
    "market": "US",
    "delivery_guard": "true"
  }
}
```

## Manual tests

When using the GitHub Actions UI manually, leave `delivery_guard` unchecked. This preserves the ability to run a manual test even if that day's scheduled report has already been sent.

## Recommended cron-job.org settings for KR

- URL: endpoint above
- Method: POST
- Schedule: 15:40, Monday-Friday
- Time zone: Asia/Seoul if available; otherwise use 06:40 UTC
- Headers: the four headers above
- Body: Korean market JSON above
- Success status: GitHub returns HTTP 204 when the workflow dispatch is accepted
