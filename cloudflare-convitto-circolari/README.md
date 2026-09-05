# Monitor circolari Convitto Rinaldo Corso — Cloudflare Workers

Monitora il feed RSS ufficiale delle circolari:

https://www.convittocorreggio.edu.it/circolare/feed/

Il Worker viene eseguito ogni minuto e invia su Telegram le nuove circolari. Alla prima esecuzione memorizza lo storico presente senza inviare notifiche arretrate.

## Configurazione Cloudflare

1. Crea/accedi a un account Cloudflare.
2. Vai in **Workers & Pages** → **Create application** → **Import a repository**.
3. Collega GitHub e seleziona `saveriodangelo-cyber/Notizie-Istruzione-Modena`.
4. Imposta come **Root directory**: `cloudflare-convitto-circolari`.
5. Il nome del Worker deve essere `convitto-circolari`.
6. Salva e distribuisci.
7. Nel Worker vai in **Settings → Variables and Secrets** e aggiungi come *Secret*:
   - `TELEGRAM_BOT_TOKEN`
   - `TELEGRAM_CHAT_ID`
8. Dopo aver salvato i secrets, il cron `* * * * *` controllerà il feed ogni minuto.

Aprendo l'URL `workers.dev` del Worker si vede lo stato del monitor, l'ultimo controllo e le ultime circolari memorizzate.

## Perché usa il feed RSS

Il feed restituisce `ETag` e `Last-Modified`. Il Worker usa richieste condizionali (`If-None-Match` e `If-Modified-Since`), quindi quando non è cambiato nulla il server può rispondere `304 Not Modified` senza riscaricare tutte le circolari.

Lo stato è salvato in un Durable Object SQLite di Cloudflare, senza dipendere da GitHub Actions o da un computer acceso.
