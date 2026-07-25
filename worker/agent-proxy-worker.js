/**
 * DeepSeek 金鑰代理 · Cloudflare Worker
 * ------------------------------------------------------------
 * 這支程式只做一件事：幫前端補上金鑰，把請求轉給 DeepSeek。
 * 它不碰任何資料、不知道商品或門市是什麼，工具查詢全部在瀏覽器端執行。
 *
 * 金鑰不寫在這個檔案裡。部署完之後到 Worker 的
 *   Settings → Variables and Secrets → Add → 型別選 Secret
 * 新增兩個：
 *   DEEPSEEK_API_KEY   你的 DeepSeek 金鑰
 *   DEMO_PASSCODE      展示通行碼（自己想一組，別人猜不到就好）
 *
 * ★ 只有下面這一行需要你改：把網址換成你的 GitHub Pages 網址。
 */
const ALLOWED_ORIGINS = [
  "https://你的帳號.github.io",   // ← 改這裡
  "http://localhost:8000",        // 本機測試用，可留著
];

const MODEL = "deepseek-v4-flash";
const ENDPOINT = "https://api.deepseek.com/chat/completions";

// 每次呼叫的硬上限，避免無限迴圈或超長 prompt 燒錢
const MAX_TOKENS = 800;
const MAX_MESSAGES = 24;
const MAX_CHARS = 24000;
const RATE_LIMIT_PER_MIN = 10;

// 簡易流量限制（同一 IP 每分鐘次數）。最終的花費上限請到 DeepSeek 後台設。
const hits = new Map();
function rateLimited(ip) {
  const now = Date.now();
  const bucket = (hits.get(ip) || []).filter((t) => now - t < 60000);
  if (bucket.length >= RATE_LIMIT_PER_MIN) return true;
  bucket.push(now);
  hits.set(ip, bucket);
  if (hits.size > 5000) hits.clear();
  return false;
}

function corsHeaders(origin) {
  return {
    "Access-Control-Allow-Origin": ALLOWED_ORIGINS.includes(origin) ? origin : "null",
    "Access-Control-Allow-Methods": "POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
    "Access-Control-Max-Age": "86400",
  };
}

function reply(status, payload, origin) {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { "Content-Type": "application/json", ...corsHeaders(origin) },
  });
}

export default {
  async fetch(request, env, ctx) {
    const origin = request.headers.get("Origin") || "";

    if (request.method === "OPTIONS") {
      return new Response(null, { status: 204, headers: corsHeaders(origin) });
    }
    if (request.method !== "POST") {
      return reply(405, { error: "只接受 POST" }, origin);
    }
    if (!ALLOWED_ORIGINS.includes(origin)) {
      return reply(403, { error: "來源不在允許清單" }, origin);
    }

    const ip = request.headers.get("CF-Connecting-IP") || "unknown";
    if (rateLimited(ip)) {
      return reply(429, { error: "請求過於頻繁，請稍候再試" }, origin);
    }

    let body;
    try {
      body = await request.json();
    } catch {
      return reply(400, { error: "格式錯誤" }, origin);
    }

    // 通行碼比對。通行碼存在 Cloudflare，不會出現在靜態網頁裡。
    if (!env.DEMO_PASSCODE || body.passcode !== env.DEMO_PASSCODE) {
      return reply(401, { error: "通行碼不正確" }, origin);
    }

    const messages = Array.isArray(body.messages) ? body.messages : null;
    if (!messages || messages.length === 0) {
      return reply(400, { error: "缺少對話內容" }, origin);
    }
    if (messages.length > MAX_MESSAGES) {
      return reply(400, { error: "對話輪數超過上限" }, origin);
    }
    if (JSON.stringify(messages).length > MAX_CHARS) {
      return reply(400, { error: "內容長度超過上限" }, origin);
    }

    // 只轉送白名單欄位，不讓前端指定模型或放大 token 上限
    const payload = {
      model: MODEL,
      messages,
      max_tokens: MAX_TOKENS,
      temperature: 0.2,
    };
    if (Array.isArray(body.tools) && body.tools.length) {
      payload.tools = body.tools;
      payload.tool_choice = "auto";
    }

    try {
      const upstream = await fetch(ENDPOINT, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${env.DEEPSEEK_API_KEY}`,
        },
        body: JSON.stringify(payload),
      });

      if (!upstream.ok) {
        // 不把上游的原始錯誤回傳，避免任何內容外洩
        console.log("upstream error", upstream.status);
        return reply(502, { error: `模型服務回應異常（${upstream.status}）` }, origin);
      }

      const data = await upstream.json();
      return reply(200, data, origin);
    } catch (err) {
      console.log("proxy error", String(err));
      return reply(500, { error: "代理發生錯誤" }, origin);
    }
  },
};
