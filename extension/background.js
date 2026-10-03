/**
 * Background Service Worker for Luga Assist Extension.
 * 1. Automatically extracts Google session cookies (__Secure-1PSID) from Chrome.
 * 2. Syncs cookies to Local Server so Gemini runs 100% in the background without ANY tabs.
 * 3. Maintains WebSocket connection to Local Agent.
 */

let ws = null;
let isConnected = false;
let sessionSynced = false;

// 1. Extract Cookies and Send to Local Server
async function syncCookiesWithServer() {
  console.log("[Luga Assist] Đang quét cookie Google trong Chrome...");
  try {
    let secure_1psid = "";
    let secure_1psidts = "";

    // Search across all Google domains for __Secure-1PSID
    const psidCookies = await chrome.cookies.getAll({ name: "__Secure-1PSID" });
    for (const c of psidCookies) {
      if (c.domain.includes("google.com") && c.value) {
        secure_1psid = c.value;
        console.log(`[Luga Assist] Tìm thấy __Secure-1PSID trên domain: ${c.domain}`);
        break;
      }
    }

    // Search for __Secure-1PSIDTS
    const psidtsCookies = await chrome.cookies.getAll({ name: "__Secure-1PSIDTS" });
    for (const c of psidtsCookies) {
      if (c.domain.includes("google.com") && c.value) {
        secure_1psidts = c.value;
        break;
      }
    }

    // Fallback: search specifically on accounts.google.com or gemini.google.com
    if (!secure_1psid) {
      const gCookie = await chrome.cookies.get({ url: "https://gemini.google.com", name: "__Secure-1PSID" })
                   || await chrome.cookies.get({ url: "https://accounts.google.com", name: "__Secure-1PSID" })
                   || await chrome.cookies.get({ url: "https://google.com", name: "__Secure-1PSID" });
      if (gCookie) secure_1psid = gCookie.value;
    }

    if (secure_1psid) {
      console.log("[Luga Assist] ✅ Đã có session Google! Đang gửi tới Local Server...");
      const res = await fetch("http://127.0.0.1:8000/api/set_session", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          secure_1psid: secure_1psid,
          secure_1psidts: secure_1psidts,
        }),
      });

      if (res.ok) {
        sessionSynced = true;
        chrome.action.setBadgeText({ text: "ON" });
        chrome.action.setBadgeBackgroundColor({ color: "#10B981" }); // Emerald Green
        console.log("[Luga Assist] 🎉 Đồng bộ session thành công! Gemini đang chạy ngầm 100%.");
        return { success: true, hasCookie: true };
      } else {
        console.warn("[Luga Assist] Server phản hồi không thành công:", res.status);
      }
    } else {
      console.warn("[Luga Assist] ⚠️ Chưa tìm thấy cookie __Secure-1PSID. Người dùng chưa đăng nhập Google trên Chrome.");
      chrome.action.setBadgeText({ text: "LOGIN" });
      chrome.action.setBadgeBackgroundColor({ color: "#F59E0B" }); // Amber
      return { success: false, hasCookie: false };
    }
  } catch (err) {
    console.error("[Luga Assist] Lỗi khi đồng bộ cookies:", err);
  }
  return { success: false, hasCookie: false };
}

// 2. Connect WebSocket to Local Agent directly from Service Worker
function connectWebSocket() {
  if (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) {
    return;
  }

  try {
    ws = new WebSocket("ws://127.0.0.1:8000/ws/extension");

    ws.onopen = () => {
      isConnected = true;
      console.log("[Luga Assist] ✅ WebSocket kết nối thành công từ Background Service Worker!");
      syncCookiesWithServer();
    };

    ws.onclose = () => {
      isConnected = false;
      setTimeout(connectWebSocket, 4000);
    };

    ws.onerror = (err) => {
      // Server may be starting
    };

    ws.onmessage = async (event) => {
      try {
        const data = JSON.parse(event.data);
        if (data.type === "SYNC_COOKIES") {
          await syncCookiesWithServer();
        }
      } catch (e) {}
    };
  } catch (e) {
    setTimeout(connectWebSocket, 4000);
  }
}

// 3. Persistent Alarm (Keepalive for Manifest V3)
chrome.alarms.create("lugaSyncAlarm", { periodInMinutes: 1 });

chrome.alarms.onAlarm.addListener((alarm) => {
  if (alarm.name === "lugaSyncAlarm") {
    connectWebSocket();
    syncCookiesWithServer();
  }
});

// Initial triggers
chrome.runtime.onInstalled.addListener(() => {
  console.log("[Luga Assist] Extension đã cài đặt.");
  connectWebSocket();
  syncCookiesWithServer();
});

chrome.runtime.onStartup.addListener(() => {
  connectWebSocket();
  syncCookiesWithServer();
});

// Listen to messages from popup
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.type === "CHECK_NOW") {
    syncCookiesWithServer().then((res) => {
      sendResponse(res);
    });
    return true; // Keep message channel open for async response
  }
  sendResponse({ received: true });
});

// Start immediately
connectWebSocket();
syncCookiesWithServer();
