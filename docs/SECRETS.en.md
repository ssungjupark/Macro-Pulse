**Language:** [한국어](SECRETS.md) | **English**

# GitHub Secrets

Path:
`Settings` -> `Secrets and variables` -> `Actions` -> `New repository secret`

## Required

### Telegram

- `TELEGRAM_BOT_TOKEN`: BotFather token
- `TELEGRAM_CHAT_ID`: destination chat or channel ID

### Gemini

- `GEMINI_API_KEY`: used for news summaries and major-event result extraction

### KRX

Used only by the Korean close workflow.

- `KRX_ID`: KRX information-data-system login ID
- `KRX_PW`: KRX information-data-system login password

Do not commit or paste secret values into source files or chat.
