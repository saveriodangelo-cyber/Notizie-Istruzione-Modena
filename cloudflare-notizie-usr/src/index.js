const SOURCES = [
  {
    name: "Ufficio scolastico territoriale di Modena",
    feed: "https://mo.istruzioneer.gov.it/category/notizie-in-evidenza/feed/",
    emoji: "📍",
  },
  {
    name: "Ufficio scolastico territoriale di Reggio Emilia",
    feed: "https://re.istruzioneer.gov.it/category/notizie-in-evidenza/feed/",
    emoji: "📌",
  },
  {
    name: "USR Emilia-Romagna",
    feed: "https://www.istruzioneer.gov.it/category/notizie-in-evidenza/feed/",
    emoji: "🏛️",
  },
];

const MAX_SEEN_PER_SOURCE = 200;

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
  const response = await fetch(`https://api.telegram.org/bot${token}/getUpdates?limit=30&timeout=0`, {
    headers: { "cache-control": "no-cache" },
  });
  if (!response.ok) {
    throw new Error(`Telegram getUpdates HTTP ${response.status}: ${await response.text()}`);
  }

  const data = await response.json();
  const updates = Array.isArray(data.result) ? data.result : [];
  console.log("telegram-updates", updates.length);

  for (const update of [...updates].reverse()) {
    const message = update.message || update.edited_message;
    const chat = message?.chat;
    if (chat?.id && chat?.type === "private") return String(chat.id);
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

async function sendNews(env, chatId, source, item) {
  const when = formatDate(item.pubDate);
  const text = [
    `${source.emoji} Nuova notizia in evidenza`,
    "",
    `Sito: ${source.name}`,
    `Titolo: ${item.title}`,
    when ? `Data: ${when}` : "",
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
        return Response.json(await this.checkNews());
      } catch (error) {
        console.error("check-error", error);
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

    const current = (await this.state.storage.get("monitor")) || { sources: {} };
    const safe = { ...current };
    delete safe.telegramChatId;
    safe.telegramChatConfigured = Boolean(current.telegramChatId || this.env.TELEGRAM_CHAT_ID);
    return Response.json(safe);
  }

  async checkNews() {
    const now = new Date().toISOString();
    const previous = (await this.state.storage.get("monitor")) || { sources: {} };
    previous.sources ||= {};

    console.log("check-start", {
      hasToken: Boolean(this.env.TELEGRAM_BOT_TOKEN),
      hasStoredChat: Boolean(previous.telegramChatId),
      hasEnvChat: Boolean(this.env.TELEGRAM_CHAT_ID),
    });

    if (!this.env.TELEGRAM_BOT_TOKEN) {
      const state = {
        ...previous,
        lastCheckedAt: now,
        lastResult: "missing-telegram-token",
        lastError: "Impostare TELEGRAM_BOT_TOKEN nei Secrets runtime del Worker.",
      };
      await this.state.storage.put("monitor", state);
      console.log("check-result", state.lastResult);
      return state;
    }

    let chatId = this.env.TELEGRAM_CHAT_ID || previous.telegramChatId || null;
    if (!chatId) {
      chatId = await discoverTelegramChatId(this.env.TELEGRAM_BOT_TOKEN);
      if (!chatId) {
        const state = {
          ...previous,
          lastCheckedAt: now,
          lastResult: "waiting-for-telegram-start",
          lastError: "Apri il bot Telegram e invia /start oppure un messaggio.",
        };
        await this.state.storage.put("monitor", state);
        console.log("check-result", state.lastResult);
        return state;
      }
      previous.telegramChatId = chatId;
      console.log("telegram-chat-discovered", true);
    }

    if (!previous.setupNotificationSent) {
      await sendPlainTelegram(
        this.env,
        chatId,
        "✅ Monitor notizie USR attivo.\n\nControllo ogni minuto le Notizie in evidenza di Modena, Reggio Emilia e USR Emilia-Romagna."
      );
      previous.setupNotificationSent = true;
      previous.lastSetupNotificationAt = now;
    }

    const errors = [];
    let notificationsSent = 0;

    for (const source of SOURCES) {
      const sourceState = previous.sources[source.feed] || {};
      const headers = {
        "user-agent": "Mozilla/5.0 (compatible; NotizieUSRCloudflare/1.0)",
        "accept": "application/rss+xml, application/xml;q=0.9, */*;q=0.8",
        "cache-control": "no-cache",
      };
      if (sourceState.etag) headers["if-none-match"] = sourceState.etag;
      if (sourceState.lastModified) headers["if-modified-since"] = sourceState.lastModified;

      try {
        const response = await fetch(source.feed, { headers });
        if (response.status === 304) {
          previous.sources[source.feed] = {
            ...sourceState,
            name: source.name,
            lastCheckedAt: now,
            lastResult: "not-modified",
            lastError: null,
          };
          continue;
        }
        if (!response.ok) throw new Error(`Feed HTTP ${response.status}`);

        const items = parseFeed(await response.text());
        if (!items.length) throw new Error("Feed RSS valido ma senza notizie leggibili.");

        const seen = new Set(sourceState.seen || []);
        const newItems = items.filter((item) => !seen.has(item.link));
        const initialized = Boolean(sourceState.initialized);

        if (initialized) {
          for (const item of [...newItems].reverse()) {
            await sendNews(this.env, chatId, source, item);
            notificationsSent += 1;
          }
        }

        previous.sources[source.feed] = {
          initialized: true,
          name: source.name,
          etag: response.headers.get("etag") || sourceState.etag || null,
          lastModified: response.headers.get("last-modified") || sourceState.lastModified || null,
          lastCheckedAt: now,
          lastResult: initialized ? (newItems.length ? "notified" : "no-new-items") : "initialized-without-notifying-history",
          lastError: null,
          seen: [...new Set([...items.map((x) => x.link), ...(sourceState.seen || [])])].slice(0, MAX_SEEN_PER_SOURCE),
          latest: items.slice(0, 10),
        };
      } catch (error) {
        const message = `${source.name}: ${String(error?.message || error)}`;
        errors.push(message);
        previous.sources[source.feed] = {
          ...sourceState,
          name: source.name,
          lastCheckedAt: now,
          lastResult: "error",
          lastError: message,
        };
      }
    }

    const errorSignature = errors.join(" | ");
    if (errors.length && errorSignature !== previous.lastErrorSignature) {
      await sendPlainTelegram(
        this.env,
        chatId,
        `⚠️ Monitor notizie USR: controllo parziale non riuscito.\n\n${errors.map((x) => `- ${x}`).join("\n")}`
      );
    }

    const state = {
      ...previous,
      telegramChatId: chatId,
      lastCheckedAt: now,
      lastResult: errors.length ? "completed-with-errors" : (notificationsSent ? "notified" : "ok"),
      lastError: errors.length ? errors.join(" | ") : null,
      lastErrorSignature: errorSignature || null,
      notificationsSentLastRun: notificationsSent,
    };

    await this.state.storage.put("monitor", state);
    console.log("check-result", state.lastResult, "notifications", notificationsSent);
    return state;
  }
}

function stateStub(env) {
  const id = env.STATE_STORE.idFromName("usr-emilia-romagna-news");
  return env.STATE_STORE.get(id);
}

export default {
  async scheduled(_controller, env, ctx) {
    console.log("scheduled-env", { hasToken: Boolean(env.TELEGRAM_BOT_TOKEN) });
    ctx.waitUntil(stateStub(env).fetch("https://state.local/check"));
  },

  async fetch(_request, env) {
    const response = await stateStub(env).fetch("https://state.local/status");
    const data = await response.json();
    return Response.json({
      service: "Monitor Notizie in evidenza - USR Emilia-Romagna",
      schedule: "ogni minuto",
      monitoredSources: SOURCES.map((x) => x.name),
      ...data,
    });
  },
};
