# Railway bot upload

Upload this folder's contents to your GitHub repository exactly as-is, then deploy that repository in Railway.

The included runtime pin uses Python 3.12.11. Do not change it back to 3.12.0: Railway's current installer rejects that older package because its download has no GitHub attestation.

Set these Railway variables:

- `DISCORD_TOKEN`
- `OWNER_IDS`
- `DASHBOARD_ACCESS_KEY`
- `PREMIUM_WEBHOOK_SECRET`

Railway supplies `PORT` automatically. Once deployed, open `https://YOUR-RAILWAY-DOMAIN/?key=YOUR_DASHBOARD_ACCESS_KEY` for the dashboard.

The premium webhook URL is `https://YOUR-RAILWAY-DOMAIN/webhooks/premium`.
