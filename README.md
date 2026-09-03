**Language:** **한국어** | [English](docs/README.en.md)

# Macro Pulse Bot

Macro Pulse Bot은 시장 매크로 지표와 지수 히트맵을 종합한 보고서를 텔레그램으로 발송하는 자동화 프로젝트입니다.

- 주요 지표를 수집합니다.
- HTML 리포트를 만듭니다.
- 텔레그램으로 보낼 수 있습니다.
- GitHub Actions로 정해진 시간에 자동 실행할 수 있습니다.

## 주요 기능

- 한국장(`KR`) 또는 미국장(`US`) 기준으로 리포트를 만듭니다.
- 주가지수, 환율, 금리, 원자재, 비트코인 같은 지표를 모읍니다.
- 텔레그램용 짧은 요약과 HTML 리포트를 함께 만듭니다.
- 주요 자산의 전일·5일·20일 변화와 20일 변동성 이상 신호를 계산합니다.
- 허용 출처와 교차검증을 통과한 뉴스만 시장 해석에 사용합니다.
- 공식 일정과 한국투자증권 시세 데이터를 별도 계층에서 수집하며, 전체 수집 실패 시 해당 섹션에 `N/A` 한 줄만 표시합니다.
- 시장 분위기를 보기 위한 스크린샷도 붙일 수 있습니다.
  - `KR`: KOSPI / KOSDAQ 히트맵
  - `US`: Finviz 맵

## 동작 방식

1. Yahoo Finance, CNBC, FRED, 한국투자 Open API에서 무료 시장 데이터를 가져옵니다.
2. 이상 범위, 기준 거래일, 오래된 데이터와 누락값을 검사합니다.
3. Google News RSS에서 허용 출처만 남기고 공식 자료 1곳 또는 언론 2곳으로 검증합니다.
4. BLS 공식 iCal과 검증 URL이 있는 일정에서 다음 주요 일정을 선택합니다.
5. HTML 리포트와 텔레그램 요약을 만들고 필요하면 전송합니다.

실제 실행 파일은 [`src/main.py`](src/main.py)입니다.

## 수집 항목

- 국내 지수: `KOSPI`, `KOSDAQ`
- 해외 지수: `S&P 500`, `Nasdaq`, `SOX`, `Russell 2000`, `Nikkei 225` 등
- 미국 국채: CNBC `2Y`, `10Y`, `30Y`, `10Y-2Y Spread`, FRED 기간별 변화
- 원자재: `WTI`, `Gold`, `Silver`, `Copper`
- 달러: `DXY`
- 환율: `USD/KRW`, `JPY/KRW`, `EUR/KRW`, `CNY/KRW`
- 가상자산: `Bitcoin`, `Ethereum`
- 변동성: `VIX`, `VKOSPI`, `MOVE`
- 국내 수급/시장 체력: 한국투자 Open API 외국인 및 기관 현물, KOSPI 프로그램 차익 및 비차익,
  상승·하락 종목 수, 거래대금, 업종 수익률 상·하위 3개

시세 전용 공식 응답을 확인하지 못한 KOSPI200 선물 수급과 52주 신고가 및
신저가는 기사 숫자로 대체하지 않습니다. 해당 항목은 보고서에서 제외하고 이유를
로그에 남깁니다. 국내 수급 조회에는 계좌번호와 주문 권한을 사용하지 않습니다.

## 뉴스 검증 원칙

- 글로벌 뉴스: Reuters, Bloomberg, Financial Times, WSJ, CNBC, AP
- 공식 자료: Fed, 미 재무부, BLS, BEA, EIA, ECB, BOJ, 한국은행, KRX, SEC
- 국내 보조 출처: KR 모드의 연합뉴스
- 기업 자료: 기업 Investor Relations
- 공식 자료는 1곳, 일반 언론은 서로 다른 허용 출처 2곳이 확인해야 분석에 사용합니다.
- 네이트, 블로그, 커뮤니티, 증권방송과 출처 불명 자료는 제외합니다.

## GitHub Actions

이 저장소는 GitHub Actions를 사용합니다.

- 정해진 시간에 자동으로 리포트를 만듭니다.
- 최신 리포트를 GitHub Pages에 올릴 수 있습니다.
- 실행 로그와 결과 파일을 artifact로 저장합니다.
- 실패하면 Telegram으로 알림을 보내도록 설정할 수 있습니다.
- 한국장 리포트는 평일 16:30 KST, 미국장 리포트는 화~토 06:30 KST에 실행합니다.
- `Run workflow`에서는 `AUTO`, `KR`, `US` 중 실행 모드를 직접 선택할 수 있습니다.

TELEGRAM Token등 KEY 설정은 [`docs/SECRETS.md`](docs/SECRETS.md)에서 볼 수 있습니다.

## 포맷 설정

텔레그램 요약 순서, 스크린샷 종류, KR/US 스케줄은 [`config/report_formats.json`](config/report_formats.json)에서 바꿀 수 있습니다.
검증된 정책·지표·기업 일정은 [`config/official_events.json`](config/official_events.json)에 공식 URL과 함께 관리합니다. 연도가 바뀌면 각 기관의 발표 일정을 확인해 이 파일을 갱신해야 합니다.

- 어떤 섹션을 먼저 보여줄지
- 어떤 항목을 포함할지
- 어떤 스크린샷을 붙일지
- KR/US 리포트가 실행될 cron 시간

## Fork 설정

Fork해서 바로 쓰려면 아래만 먼저 설정하면 됩니다.

1. Fork한 저장소의 `Actions` 탭에서 워크플로를 활성화합니다.
2. `Settings > Secrets and variables > Actions`에서 Telegram 및 한국투자 Open API Secret을 등록합니다.
3. 웹 리포트도 보고 싶다면 `Settings > Pages`에서 source를 `GitHub Actions`로 설정합니다.
4. 필요하면 [`config/report_formats.json`](config/report_formats.json)에서 KR/US 포맷과 스케줄을 바꿉니다.

## 로컬 / Docker 실행

자세한 실행 방법은 [`docs/LOCAL_RUN.md`](docs/LOCAL_RUN.md)에서 볼 수 있습니다.

> 빠른 미리보기
>
> - 설치: `uv sync --all-groups`
> - Python dry-run: `uv run python src/main.py --dry-run`
> - Docker build: `docker build -t macro-pulse .`
> - Docker dry-run: `docker run --rm --env-file .env -v "$PWD:/app" -w /app macro-pulse uv run --frozen python src/main.py --dry-run`

## 테스트

기본 테스트:

```bash
uv run python -m unittest discover tests
```

실제 외부 서비스까지 확인하는 스모크 테스트:

```bash
RUN_LIVE_SMOKE_TESTS=1 uv run python -m unittest discover tests
```

스크린샷 스모크 테스트:

```bash
RUN_SCREENSHOT_SMOKE_TESTS=1 uv run python -m unittest tests.test_screenshot
```

## 스크린샷 예시

### 미장 마감 예시

![미장 마감 보고서 예시](assets/us.png)

### 국장 마감 예시

![국장 마감 보고서 예시](assets/kr.png)

## 자주 보는 파일

- [`src/main.py`](src/main.py): 전체 실행 시작점
- [`src/macro_pulse/data/market_data.py`](src/macro_pulse/data/market_data.py): 데이터 수집 orchestration
- [`src/macro_pulse/reporting/generator.py`](src/macro_pulse/reporting/generator.py): 리포트 생성
- [`src/macro_pulse/delivery/notifier.py`](src/macro_pulse/delivery/notifier.py): 텔레그램 전송
- [`config/report_formats.json`](config/report_formats.json): 요약 포맷 설정

## 문제 해결

- 스크린샷이 실패하면 Chrome/Chromium 실행 환경을 먼저 확인하세요.
- 텔레그램 메시지가 안 오면 `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`를 확인하세요.
- 일부 데이터가 비어 있으면 외부 사이트 응답 문제일 수 있습니다.
- GitHub Pages가 안 보이면 `Settings > Pages`에서 source가 `GitHub Actions`로 설정되어 있는지 확인하세요.

## 면책조항

해당 저장소는 규칙 기반 자동화 워크플로우와 구현 방법을 공유하기 위한 프로젝트입니다.  
실제 투자 판단을 위한 자문, 권유, 보장된 신호 제공을 목적으로 하지 않습니다.  
실행 및 활용에 따른 책임은 사용자 본인에게 있습니다.  
