const FEED_URL = "https://www.convittocorreggio.edu.it/circolare/feed/";
const MAX_SEEN = 100;

function decodeEntities(value = "") {
  return value
    .replace(/<!\[CDATA\[([\s\S]*?)\]\]>/g, "$1")
    .replace(/&#(\d+);/g, (_, n) => String.fromCodePoint(Number(n)))
    .replace(/&#x([0-9a-f]+);/gi, (_, n) => String.fromCodePoint(parseInt(n, 16)))
    .replace(/&amp;/g, "&")
    .replace(/&quot;/g, '"')
    .replace(/&#039;|&apos;/g, "'")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">");
}

function tagValue(xml, tag) {
  const safeTag = tag.replace(":", "\\:");
  const match = xml.match(new RegExp(`<${safeTag}(?:\\s[^>]*)?>([\\s\\S]*?)<\\/${safeTag}>`, "i"));
  return match ? decodeEntities(match[1].trim()) : "";
}

function parseFeed(xml) {
  const items = [];
  const regex = /<item>([\s\S]*?)<\/item>/gi;
  let match;
  while ((match = regex.exec(xml)) && items.length < 30) {
    const block = match[1];
    const title = tagValue(block, "title");
    const link = tagValue(block, "link");
    const pubDate = tagValue(block, "pubDate");
    if (title && link) items.push({ title, link, pubDate });
  }
  return items;
}

function formatDate(pubDate) {
  if (!pubDate) return "";
  const d = new Date(pubDate);
  if (Number.isNaN(d.getTime())) return pubDate;
  return new Intl.DateTimeFormat("it-IT", {
    timeZone: "Europe/Rome",
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(d);
}

async function discoverTelegramChatId(token) {
  const response = await fetch(`https://api.telegram.org/bot${token}/getUpdates?limit=20&timeout=0`, {
    headers: { "cache-control": "no-cache" },
  });
  if (!response.ok) {
    throw new Error(`Telegram getUpdates HTTP ${response.status}: ${await response.text()}`);
  }

  const data = await response.json();
  const updates = Array.isArray(data.result) ? data.result : [];

  for (const update of [...updates].reverse()) {
    const message = update.message || update.edited_message;
    const chat = message?.chat;
    if (chat?.id && chat?.type === "private") {
      return String(chat.id);
    }
  }
  return null;
}

async function sendPlainTelegram(env, chatId, text) {
  const response = await fetch(`https://api.telegram.org/bot${env.TELEGRAM_BOT_TOKEN}/sendMessage`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({
      chat_id: chatId,
      text,
      disable_web_page_preview: false,
    }),
  });

  if (!response.ok) {
    throw new Error(`Telegram HTTP ${response.status}: ${await response.text()}`);
  }
}

async function sendTelegram(env, chatId, item) {
  const when = formatDate(item.pubDate);
  const text = [
    "🏫 Nuova circolare — Rinaldo Corso",
    "",
    item.title,
    when ? `Pubblicata: ${when}` : "",
    "",
    item.link,
  ].filter(Boolean).join("\n");

  await sendPlainTelegram(env, chatId, text);
}

export class StateStore {
  constructor(state, env) {
    this.state = state;
    this.env = env;
  }

  async fetch(request) {
    const url = new URL(request.url);

    if (url.pathname === "/check") {
      try {
        const result = await this.checkCircolari();
        return Response.json(result);
      } catch (error) {
        console.error(error);
        const previous = (await this.state.storage.get("monitor")) || {};
        const failed = {
          ...previous,
          lastCheckedAt: new Date().toISOString(),
          lastResult: "error",
          lastError: String(error?.message || error),
        };
        await this.state.storage.put("monitor", failed);
        return Response.json(failed, { status: 500 });
      }
    }

    const current = (await this.state.storage.get("monitor")) || {
      initialized: false,
      feed: FEED_URL,
    };

    const safe = { ...current };
    delete safe.telegramChatId;
    safe.telegramChatConfigured = Boolean(current.telegramChatId || this.env.TELEGRAM_CHAT_ID);
    return Response.json(safe);
  }

  async checkCircolari() {
    const now = new Date().toISOString();
    const previous = (await this.state.storage.get("monitor")) || {};

    if (!this.env.TELEGRAM_BOT_TOKEN) {
      const state = {
        ...previous,
        feed: FEED_URL,
        lastCheckedAt: now,
        lastResult: "missing-telegram-token",
        lastError: "Impostare TELEGRAM_BOT_TOKEN nei Secrets del Worker.",
      };
      await this.state.storage.put("monitor", state);
      return state;
    }

    let chatId = this.env.TELEGRAM_CHAT_ID || previous.telegramChatId || null;

    if (!chatId) {
      chatId = await discoverTelegramChatId(this.env.TELEGRAM_BOT_TOKEN);
      if (!chatId) {
        const state = {
          ...previous,
          feed: FEED_URL,
          lastCheckedAt: now,
          lastResult: "waiting-for-telegram-start",
          lastError: "Apri il bot su Telegram e premi Avvia / invia /start. Il Worker rileverà automaticamente la chat al controllo successivo.",
        };
        await this.state.storage.put("monitor", state);
        return state;
      }

      previous.telegramChatId = chatId;

      if (!previous.setupNotificationSent) {
        await sendPlainTelegram(
          this.env,
          chatId,
          "✅ Test riuscito — monitor circolari Rinaldo Corso attivo.\n\nDa ora controllerò automaticamente il feed delle circolari e ti avviserò quando ne verrà pubblicata una nuova."
        );
        previous.setupNotificationSent = true;
        previous.lastSetupNotificationAt = now;
      }
    }

    const headers = {
      "user-agent": "Mozilla/5.0 (compatible; CircolariConvittoCloudflare/1.2)",
      "accept": "application/rss+xml, application/xml;q=0.9, */*;q=0.8",
      "cache-control": "no-cache",
    };
    if (previous.etag) headers["if-none-match"] = previous.etag;
    if (previous.lastModified) headers["if-modified-since"] = previous.lastModified;

    const response = await fetch(FEED_URL, { headers });

    if (response.status === 304) {
      const state = {
        ...previous,
        telegramChatId: chatId,
        lastCheckedAt: now,
        lastResult: "not-modified",
        lastError: null,
      };
      await this.state.storage.put("monitor", state);
      return state;
    }

    if (!response.ok) {
      throw new Error(`Feed HTTP ${response.status}`);
    }

    const xml = await response.text();
    const items = parseFeed(xml);
    if (!items.length) throw new Error("Feed RSS valido ma senza circolari leggibili.");

    const seen = new Set(previous.seen || []);
    const newItems = items.filter((item) => !seen.has(item.link));
    const initialized = Boolean(previous.initialized);

    if (initialized) {
      for (const item of [...newItems].reverse()) {
        await sendTelegram(this.env, chatId, item);
      }
    }

    const mergedSeen = [...new Set([...items.map((x) => x.link), ...(previous.seen || [])])].slice(0, MAX_SEEN);
    const state = {
      initialized: true,
      feed: FEED_URL,
      telegramChatId: chatId,
      setupNotificationSent: previous.setupNotificationSent || false,
      lastSetupNotificationAt: previous.lastSetupNotificationAt || null,
      etag: response.headers.get("etag") || previous.etag || null,
      lastModified: response.headers.get("last-modified") || previous.lastModified || null,
      lastCheckedAt: now,
      lastResult: initialized ? (newItems.length ? "notified" : "no-new-items") : "initialized-without-notifying-history",
      lastError: null,
      lastNotificationAt: initialized && newItems.length ? now : previous.lastNotificationAt || null,
      notificationsSentLastRun: initialized ? newItems.length : 0,
      seen: mergedSeen,
      latest: items.slice(0, 10),
    };

    await this.state.storage.put("monitor", state);
    return state;
  }
}

function stateStub(env) {
  const id = env.STATE_STORE.idFromName("convitto-rinaldo-corso");
  return env.STATE_STORE.get(id);
}

export default {
  async scheduled(_controller, env, ctx) {
    ctx.waitUntil(stateStub(env).fetch("https://state.local/check"));
  },

  async fetch(_request, env) {
    const response = await stateStub(env).fetch("https://state.local/status");
    const data = await response.json();
    return Response.json({
      service: "Monitor circolari Convitto Nazionale Rinaldo Corso",
      schedule: "ogni minuto",
      ...data,
    });
  },
};
