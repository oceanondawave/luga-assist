document.addEventListener("DOMContentLoaded", () => {
  const agentDot = document.getElementById("agentDot");
  const agentStatus = document.getElementById("agentStatus");
  const geminiDot = document.getElementById("geminiDot");
  const geminiStatus = document.getElementById("geminiStatus");
  const btnSyncSession = document.getElementById("btnSyncSession");

  function refreshStatus() {
    fetch("http://127.0.0.1:8000/api/status")
      .then((res) => res.json())
      .then((data) => {
        agentDot.classList.add("connected");
        agentStatus.innerText = "Luga Assist: Đang chạy (Cổng 8000)";

        if (data.gemini_ready) {
          geminiDot.classList.add("connected");
          geminiStatus.innerText = "Google Session: Đã kết nối (Sẵn sàng)";
        } else {
          geminiDot.classList.remove("connected");
          geminiStatus.innerText = "Google Session: Đang đồng bộ...";
          chrome.runtime.sendMessage({ type: "CHECK_NOW" }, (res) => {
            if (res && res.sessionSynced) {
              geminiDot.classList.add("connected");
              geminiStatus.innerText = "Google Session: Đã kết nối (Sẵn sàng)";
            }
          });
        }
      })
      .catch(() => {
        agentDot.classList.remove("connected");
        agentStatus.innerText = "Luga Assist: Chưa bật (Hãy mở app)";
        geminiDot.classList.remove("connected");
        geminiStatus.innerText = "Google Session: Đang chờ Luga Assist...";
      });
  }

  refreshStatus();

  btnSyncSession.addEventListener("click", () => {
    geminiStatus.innerText = "Đang đồng bộ session từ Chrome...";
    chrome.runtime.sendMessage({ type: "CHECK_NOW" }, (res) => {
      if (res && res.hasCookie === false) {
        geminiStatus.innerHTML = "⚠️ Chưa đăng nhập Google. <a href='https://accounts.google.com' target='_blank' style='color:#38bdf8;'>Đăng nhập tại đây</a>";
      } else {
        setTimeout(refreshStatus, 800);
      }
    });
  });
});
