# Monitor Notizie USR Emilia-Romagna

Versione Cloudflare del vecchio bot GitHub Actions, ricostruita a partire dal codice storico precedente all'aggiunta del monitor del Convitto.

Monitora ogni minuto le categorie **Notizie in evidenza** di:

- Ufficio scolastico territoriale di Modena
- Ufficio scolastico territoriale di Reggio Emilia
- USR Emilia-Romagna

Usa i feed RSS ufficiali delle tre categorie, conserva lo stato in un Durable Object e invia su Telegram solo gli elementi nuovi dopo la prima inizializzazione.

## Deploy da Cloudflare con GitHub

Importare il repository `saveriodangelo-cyber/Notizie-Istruzione-Modena` come un nuovo progetto Worker.

- Nome progetto: `notizie-usr-emilia-romagna`
- Comando di generazione: vuoto
- Comando di distribuzione: `cd cloudflare-notizie-usr && npx wrangler deploy`
- Directory radice: `/`

Dopo il primo deploy, in **Impostazioni > Runtime variables and secrets** aggiungere:

- `TELEGRAM_BOT_TOKEN` come Secret

`TELEGRAM_CHAT_ID` è facoltativo: se assente, il Worker prova a rilevare automaticamente una chat privata dopo che l'utente invia `/start` o un messaggio al bot.

Il file `wrangler.toml` usa `keep_vars = true` per evitare che i futuri deploy eliminino i secret runtime impostati dal dashboard.
