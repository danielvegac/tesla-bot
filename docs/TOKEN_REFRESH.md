# Tesla token auto-refresh

## Why

Fleet third-party `access_token` expires in hours. Telegram can still poll while every Tesla call returns 401.

`refresh_token` is **single use**. Tesla returns a new refresh token on every exchange. Save both immediately. Unused refresh tokens last about 3 months. A just-used refresh stays valid up to 24 hours if the write failed.

Endpoint: `POST https://fleet-auth.prd.vn.cloud.tesla.com/oauth2/v3/token`

App: `TESLA_CLIENT_ID=523a361f-12e3-4f22-a95e-b71348948b51` (not 8176c514).

## Runtime

`TeslaClient._request` on HTTP 401 calls `tesla_oauth.refresh_and_persist()`, rebuilds the httpx client, retries once.

Manual:

```bash
cd ~/Desktop/tesla-familia-bot
unset TESLA_ACCESS_TOKEN TESLA_REFRESH_TOKEN
set -a && source .env && set +a
export SSL_CERT_FILE=$HOME/zscaler-chain.pem
python3 -m tesla_oauth
```

Never commit `.env`.
