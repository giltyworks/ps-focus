# PS Focus friends server

A Cloudflare Worker with a D1 database. It passes figures between people who have added each other by friend code. It runs on Cloudflare's free plan, which allows 100,000 requests a day. Each copy of PS Focus with friends on checks in about every ten minutes while it runs, so that covers well over a thousand people a day.

People are known by their Google account. Each request carries a Google ID token for the PS Focus sign-in client, which the Worker checks against Google's public keys. Only the account's ID is kept, never its email. Turning friends off deletes everything kept about the person, and a daily clean-up deletes anyone not heard from in six months.

## First deploy

Needs Node.js and a free Cloudflare account.

```powershell
cd friends_server
npm install
npx wrangler login
npx wrangler d1 create ps-focus-friends
```

Put the `database_id` it prints into `wrangler.toml`, then:

```powershell
npx wrangler d1 execute ps-focus-friends --remote --file schema.sql
npx wrangler deploy
```

Put the address it prints, `https://ps-focus-friends.<your subdomain>.workers.dev`, in `FRIENDS_SERVER_URL` in `friends.py`, and build the app.

## Updates

`npx wrangler deploy` from this folder. A change to the tables goes in `schema.sql` with `IF NOT EXISTS`, and is run with the `d1 execute` line above.

## Testing locally

```powershell
npm run dev
py test_server.py
```

The local copy keeps its own database in `.wrangler`, set up once with `npx wrangler d1 execute ps-focus-friends --local --file schema.sql`. It accepts `dev:<id>` in place of a Google token, which the deployed server never does.
