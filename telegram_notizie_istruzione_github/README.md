# Bot Telegram - Notizie in evidenza Istruzione ER

Questo progetto controlla automaticamente le sezioni **Notizie in evidenza** di:

- https://mo.istruzioneer.gov.it/
- https://www.istruzioneer.gov.it/

Quando trova una nuova notizia, manda una notifica Telegram.

La versione è pensata per **GitHub Actions**, quindi funziona anche se il PC è spento.

---

## 1. Crea il bot Telegram

1. Apri Telegram.
2. Cerca `@BotFather`.
3. Scrivi `/newbot`.
4. Scegli un nome, per esempio `Notizie Istruzione`.
5. Scegli uno username che finisca con `bot`, per esempio `notizie_istruzione_saverio_bot`.
6. Copia il token che BotFather ti dà.

Il token è simile a questo:

```text
123456789:ABCDEF...
```

---

## 2. Trova il tuo TELEGRAM_CHAT_ID

Sul PC puoi usare il file `get_chat_id.py`.

### Metodo semplice da terminale

Apri la cartella del progetto e lancia:

```bash
pip install -r requirements.txt
```

Poi crea un file `.env` copiando `.env.example` e inserisci il token:

```env
TELEGRAM_BOT_TOKEN=il_token_del_bot
TELEGRAM_CHAT_ID=
SEND_ON_FIRST_RUN=false
```

Ora esegui:

```bash
python get_chat_id.py
```

Apri Telegram, cerca il bot che hai creato e scrivigli:

```text
/start
```

Il programma ti mostrerà una riga simile:

```env
TELEGRAM_CHAT_ID=123456789
```

Copia quel numero.

---

## 3. Crea il repository GitHub

1. Vai su GitHub.
2. Crea un nuovo repository, meglio **privato**.
3. Carica tutti i file di questa cartella nel repository, compresa la cartella nascosta `.github`.

La struttura deve essere così:

```text
.github/workflows/check-news.yml
check_news_once.py
get_chat_id.py
requirements.txt
seen_news.json
README.md
```

---

## 4. Aggiungi i Secrets su GitHub

Nel repository vai su:

```text
Settings → Secrets and variables → Actions → New repository secret
```

Crea questi due secrets:

```text
TELEGRAM_BOT_TOKEN
```

con dentro il token del bot.

Poi:

```text
TELEGRAM_CHAT_ID
```

con dentro il tuo chat ID.

---

## 5. Attiva GitHub Actions

Vai nella scheda:

```text
Actions
```

Se GitHub te lo chiede, abilita i workflow.

Poi apri il workflow:

```text
Controlla notizie in evidenza
```

e clicca:

```text
Run workflow
```

La prima esecuzione memorizza le notizie già presenti senza notificare, così non ti arrivano subito messaggi vecchi.

Dopo, il controllo parte automaticamente ogni 30 minuti.

---

## 6. Vuoi ricevere anche le notizie già presenti alla prima esecuzione?

Apri il file:

```text
.github/workflows/check-news.yml
```

Cambia questa riga:

```yaml
SEND_ON_FIRST_RUN: "false"
```

in:

```yaml
SEND_ON_FIRST_RUN: "true"
```

Poi fai commit.

---

## Note importanti

- GitHub Actions usa l'orario UTC.
- Il controllo è impostato ogni 30 minuti.
- Lo storico delle notizie già viste viene salvato in `seen_news.json`.
- Non inserire mai il token Telegram nei file pubblici del repository.
- Se il repository è pubblico, usa comunque sempre i Secrets.

---

## Test locale rapido

Con `.env` compilato, puoi provare anche dal PC:

```bash
pip install -r requirements.txt
python check_news_once.py
```
