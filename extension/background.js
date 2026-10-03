/**
 * Background Service Worker for Luga Assist Extension.
 * 1. Safely checks if Local Server (port 8000) is online.
 * 2. Automatically extracts Google session cookies (__Secure-1PSID) from Chrome.
 * 3. Syncs cookies to Local Server so Gemini runs 100% in the background without ANY tabs.
 * 4. Maintains WebSocket connection to Local Agent only when server is up (prevents ERR_CONNECTION_REFUSED).
 */

let ws = null;
let isConnected = false;
let sessionSynced = false;

// Helper: Check if local agent server is alive before attempting connections
async function isServerRunning() {
  try {
    const res = await fetch("http://127.0.0.1:8000/api/status", { method: "GET" });
    return res.ok;
  } catch (e) {
    // Normal when user hasn't run ./start.sh yet
    return false;
  }
}

// 1. Extract Cookies and Send to Local Server
async function syncCookiesWithServer() {
  const serverAlive = await isServerRunning();
  if (!serverAlive) {
    // Server is offline, update badge quietly without logging any error
    chrome.action.setBadgeText({ text: "OFF" });
    chrome.action.setBadgeBackgroundColor({ color: "#6B7280" }); // Gray
    return { success: false, hasCookie: false, serverOffline: true };
  }

  try {
    let secure_1psid = "";
    let secure_1psidts = "";

    // Search across all Google domains for __Secure-1PSID
    const psidCookies = await chrome.cookies.getAll({ name: "__Secure-1PSID" });
    for (const c of psidCookies) {
      if (c.domain && c.domain.includes("google.com") && c.value) {
        secure_1psid = c.value;
        break;
      }
    }

    // Search for __Secure-1PSIDTS
    const psidtsCookies = await chrome.cookies.getAll({ name: "__Secure-1PSIDTS" });
    for (const c of psidtsCookies) {
      if (c.domain && c.domain.includes("google.com") && c.value) {
        secure_1psidts = c.value;
        break;
      }
    }

    // Fallback: search specifically on accounts or gemini
    if (!secure_1psid) {
      const gCookie = await chrome.cookies.get({ url: "https://gemini.google.com", name: "__Secure-1PSID" })
                   || await chrome.cookies.get({ url: "https://accounts.google.com", name: "__Secure-1PSID" })
                   || await chrome.cookies.get({ url: "https://google.com", name: "__Secure-1PSID" });
      if (gCookie) secure_1psid = gCookie.value;
    }

    if (secure_1psid) {
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
        console.log("[Luga Assist] Đồng bộ session Google thành công! Gemini chạy ngầm 100%.");
        return { success: true, hasCookie: true };
      }
    } else {
      chrome.action.setBadgeText({ text: "LOGIN" });
      chrome.action.setBadgeBackgroundColor({ color: "#F59E0B" }); // Amber
      return { success: false, hasCookie: false };
    }
  } catch (err) {
    // Log as debug, not console.error to keep chrome://extensions completely clean
    console.debug("[Luga Assist] Đang chờ server...", err);
  }
  return { success: false, hasCookie: false };
}

// 2. Connect WebSocket to Local Agent ONLY when server is running
async function connectWebSocket() {
  if (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) {
    return;
  }

  // Pre-flight check: do NOT open WebSocket if server port 8000 is closed
  const serverAlive = await isServerRunning();
  if (!serverAlive) {
    setTimeout(connectWebSocket, 4000);
    return;
  }

  try {
    ws = new WebSocket("ws://127.0.0.1:8000/ws/extension");

    ws.onopen = () => {
      isConnected = true;
      console.log("[Luga Assist] WebSocket kết nối thành công từ Background Service Worker!");
      syncCookiesWithServer();
    };

    ws.onclose = () => {
      isConnected = false;
      setTimeout(connectWebSocket, 4000);
    };

    ws.onerror = () => {
      // Handled silently
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

// 3. Keepalive Alarm for Service Worker
chrome.alarms.create("lugaSyncAlarm", { periodInMinutes: 1 });

chrome.alarms.onAlarm.addListener((alarm) => {
  if (alarm.name === "lugaSyncAlarm") {
    connectWebSocket();
    syncCookiesWithServer();
  }
});

// Initial triggers
chrome.runtime.onInstalled.addListener(() => {
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
    return true;
  }
  sendResponse({ received: true });
});

// Start checking
connectWebSocket();
syncCookiesWithServer();
