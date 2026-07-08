# Bot notizie in evidenza - Telegram + Email

Questo progetto controlla periodicamente le sezioni **Notizie in evidenza** di:

- https://mo.istruzioneer.gov.it/
- https://www.istruzioneer.gov.it/

Quando trova una nuova notizia, può inviare una notifica su Telegram, via email, oppure entrambe.

## Come funziona su GitHub Actions

Il file `.github/workflows/check-news.yml` avvia il controllo ogni 30 minuti.

Il file `seen_news.json` salva le notizie già viste, così il bot non manda sempre le stesse notifiche.

La prima esecuzione, di default, memorizza le notizie già presenti senza inviarle. Dalla seconda esecuzione in poi invia solo le novità.

## File inclusi

- `check_news_once.py` - controlla le notizie e invia notifiche
- `seen_news.json` - archivio delle notizie già viste
- `requirements.txt` - librerie Python necessarie
- `.github/workflows/check-news.yml` - automazione GitHub Actions
- `.env.example` - esempio di configurazione locale
- `get_chat_id.py` - utile per trovare il chat ID Telegram

## Secrets GitHub per Telegram

Nel repository GitHub vai su:

`Settings` → `Secrets and variables` → `Actions` → `New repository secret`

Crea questi secrets:

```text
TELEGRAM_BOT_TOKEN
TELEGRAM_CHAT_ID
```

Se vuoi usare solo email, puoi anche non creare questi due secrets.

## Secrets GitHub per Email

Per ricevere anche le email crea questi secrets:

```text
SMTP_HOST
SMTP_PORT
SMTP_USERNAME
SMTP_PASSWORD
EMAIL_FROM
EMAIL_TO
```

Esempio con Gmail:

```text
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=latuaemail@gmail.com
SMTP_PASSWORD=la_password_per_app_di_google
EMAIL_FROM=latuaemail@gmail.com
EMAIL_TO=email_dove_vuoi_ricevere@example.com
```

Esempio generico con Outlook/Hotmail/Live:

```text
SMTP_HOST=smtp.office365.com
SMTP_PORT=587
SMTP_USERNAME=latuaemail@outlook.com
SMTP_PASSWORD=password_o_password_per_app
EMAIL_FROM=latuaemail@outlook.com
EMAIL_TO=email_dove_vuoi_ricevere@example.com
```

Nota: per Gmail spesso serve una **password per app** e non la password normale dell'account. L'account Google deve avere la verifica in due passaggi attiva. Per Outlook/Live può essere necessaria una password per app se hai l'autenticazione a due fattori attiva.

## Come caricare il workflow se Windows nasconde la cartella `.github`

Se GitHub non ti carica la cartella `.github`, fai così:

1. Apri il repository su GitHub.
2. Clicca `Add file` → `Create new file`.
3. Come nome file scrivi esattamente:

```text
.github/workflows/check-news.yml
```

4. Incolla il contenuto del file `check-news.yml` che trovi nello zip.
5. Clicca `Commit changes`.

GitHub creerà da solo la cartella nascosta corretta.

## Avvio manuale

Vai su:

`Actions` → `Controlla notizie in evidenza` → `Run workflow`

La prima esecuzione serve soprattutto a inizializzare lo storico.

## Se non arrivano notifiche

Controlla questi punti:

1. In `Actions`, apri l'ultima esecuzione e guarda se ci sono errori rossi.
2. Verifica che i secrets siano scritti esattamente con questi nomi.
3. Se usi Gmail, verifica di aver inserito una password per app, non la password normale.
4. Se usi solo email, assicurati che siano presenti almeno `SMTP_HOST`, `SMTP_USERNAME`, `SMTP_PASSWORD` ed `EMAIL_TO`.
5. Se usi Telegram, assicurati che siano presenti `TELEGRAM_BOT_TOKEN` e `TELEGRAM_CHAT_ID`.

