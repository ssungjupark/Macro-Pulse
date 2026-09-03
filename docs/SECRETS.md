**Language:** **한국어** | [English](SECRETS.en.md)

# GitHub Secrets

GitHub Actions에서 Macro Pulse Bot을 정상적으로 실행하려면 저장소에 아래 Secret 값을 등록해야 합니다.

워크플로는 `uv.lock`을 기준으로 빌드된 런타임 이미지를 사용합니다.

경로:
`Settings` -> `Secrets and variables` -> `Actions` -> `New repository secret`

## 필수 항목

### Telegram

- `TELEGRAM_BOT_TOKEN`: BotFather로 만든 텔레그램 봇의 토큰
- `TELEGRAM_CHAT_ID`: 리포트를 받을 채팅방 또는 채널의 ID

### 한국투자 Open API

- `KIS_APP_KEY`: 한국투자 Open API 앱 키
- `KIS_APP_SECRET`: 한국투자 Open API 앱 시크릿

국내 수급과 시장 체력 조회에 사용합니다. 계좌번호, 계좌 비밀번호와 주문 권한은
등록하지 않습니다.

## 주의 사항

- Secret 이름은 위와 정확히 같아야 합니다.
