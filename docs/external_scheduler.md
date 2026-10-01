# External scheduler setup

GitHub Actions의 `schedule` 이벤트는 지정 시각보다 늦게 시작될 수 있습니다. 시장 마감 리포트처럼 시각이 중요한 작업은 외부 HTTP 스케줄러가 `workflow_dispatch`를 호출하고, GitHub cron은 백업으로 사용합니다.

## Endpoint

POST

`https://api.github.com/repos/ssungjupark/Macro-Pulse/actions/workflows/daily_report.yml/dispatches`

## Required headers

- `Accept: application/vnd.github+json`
- `Authorization: Bearer <FINE_GRAINED_GITHUB_TOKEN>`
- `X-GitHub-Api-Version: 2022-11-28`
- `Content-Type: application/json`

Fine-grained PAT은 `ssungjupark/Macro-Pulse` 저장소에만 접근하도록 제한하고, `Actions: Read and write` 권한만 부여합니다.

## 한국장

- 실행 시각: 평일 16:30 KST
- UTC: 평일 07:30

Body:

```json
{
  "ref": "main",
  "inputs": {
    "market": "KR",
    "delivery_guard": "true"
  }
}
```

## 미국장

- 실행 시각: 화~토 06:30 KST
- UTC: 월~금 21:30

Body:

```json
{
  "ref": "main",
  "inputs": {
    "market": "US",
    "delivery_guard": "true"
  }
}
```

## 중복 방지

외부 스케줄러와 GitHub backup cron은 같은 시장/보고 날짜의 cache key를 사용합니다. 먼저 성공한 실행이 텔레그램 본문 발송 기록을 저장하면 이후 실행은 자동으로 건너뜁니다.

GitHub 자체 백업 시각은 한국장 16:30, 16:45, 17:00 KST 및 미국장 06:30, 06:45, 07:00 KST입니다. GitHub 스케줄 자체가 지연될 수 있으므로 정시 발송의 주 경로는 외부 스케줄러입니다.

## 수동 테스트

GitHub Actions의 `Run workflow`에서 `delivery_guard`를 체크하지 않으면 같은 날에도 테스트 발송할 수 있습니다. 실제 정기 발송과 동일하게 중복 방지를 확인하려면 `delivery_guard=true`로 실행합니다.
