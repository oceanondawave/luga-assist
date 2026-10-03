document.addEventListener("DOMContentLoaded", () => {
  const agentDot = document.getElementById("agentDot");
  const agentStatus = document.getElementById("agentStatus");
  const geminiDot = document.getElementById("geminiDot");
  const geminiStatus = document.getElementById("geminiStatus");
  const btnOpenApp = document.getElementById("btnOpenApp");
  const btnSyncSession = document.getElementById("btnSyncSession");

  function refreshStatus() {
    fetch("http://127.0.0.1:8000/api/status")
      .then((res) => res.json())
      .then((data) => {
        agentDot.classList.add("connected");
        agentStatus.innerText = "Local Agent: Đang chạy (Cổng 8000)";

        if (data.gemini_ready) {
          geminiDot.classList.add("connected");
          geminiStatus.innerText = "Google Gemini: Đã sẵn sàng (Chạy ngầm)";
        } else {
          geminiDot.classList.remove("connected");
          geminiStatus.innerText = "Google Gemini: Đang đồng bộ Session...";
          // Auto trigger cookie sync
          chrome.runtime.sendMessage({ type: "CHECK_NOW" }, (res) => {
            if (res && res.sessionSynced) {
              geminiDot.classList.add("connected");
              geminiStatus.innerText = "Google Gemini: Đã sẵn sàng (Chạy ngầm)";
            }
          });
        }
      })
      .catch((err) => {
        agentDot.classList.remove("connected");
        agentStatus.innerText = "Local Agent: Chưa bật (Chạy ./start.sh)";
        geminiDot.classList.remove("connected");
        geminiStatus.innerText = "Google Gemini: Đang chờ Agent...";
      });
  }

  // 1. Initial check
  refreshStatus();

  // 2. Open Luga Assist
  btnOpenApp.addEventListener("click", () => {
    chrome.tabs.query({ url: "http://127.0.0.1:8000/*" }, (existingTabs) => {
      if (existingTabs && existingTabs.length > 0) {
        chrome.tabs.update(existingTabs[0].id, { active: true });
        chrome.windows.update(existingTabs[0].windowId, { focused: true });
      } else {
        chrome.tabs.create({ url: "http://127.0.0.1:8000" });
      }
      window.close();
    });
  });

  // 3. Manual sync button
  btnSyncSession.addEventListener("click", () => {
    geminiStatus.innerText = "Đang đồng bộ session từ Chrome...";
    chrome.runtime.sendMessage({ type: "CHECK_NOW" }, (res) => {
      if (res && res.hasCookie === false) {
        geminiStatus.innerHTML = "⚠️ Chưa đăng nhập Google. <a href='https://accounts.google.com' target='_blank' style='color:#60a5fa;'>Bấm vào đây để đăng nhập</a>";
      } else {
        setTimeout(refreshStatus, 800);
      }
    });
  });
});
