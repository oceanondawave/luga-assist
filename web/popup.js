/**
 * Luga Assist - Mini Floating Popup Logic
 * Full accessibility & thinking level support
 */
document.addEventListener("DOMContentLoaded", () => {
  const chatThread = document.getElementById("popupChatThread");
  const chatThinking = document.getElementById("popupThinking");
  const chatThinkingText = document.getElementById("popupThinkingText");
  const chatForm = document.getElementById("popupChatForm");
  const chatInput = document.getElementById("popupChatInput");
  const btnMic = document.getElementById("btnPopupMic");
  const chkTTS = document.getElementById("chkPopupTTS");
  const btnPopupMode = document.getElementById("btnPopupMode");
  const popupModeLabel = document.getElementById("popupModeLabel");
  const popupStatusDot = document.getElementById("popupStatusDot");
  const popupThinkingLevel = document.getElementById("popupThinkingLevel");
  const btnPopupClear = document.getElementById("btnPopupClear");
  const btnPopupGoogleAuth = document.getElementById("btnPopupGoogleAuth");

  let ws = null;
  let currentMode = "control";
  let currentThinkingLevel = "medium";
  let recognition = null;
  let isListening = false;

  function getApiUrl(endpoint) {
    const loc = window.location;
    if (loc.protocol === "file:" || !loc.port) {
      return `http://127.0.0.1:8765${endpoint}`;
    }
    return endpoint;
  }

  // Google Web Auth Button
  function updateGoogleStatus(ready) {
    if (btnPopupGoogleAuth) {
      if (ready) {
        btnPopupGoogleAuth.style.display = "none";
      } else {
        btnPopupGoogleAuth.style.display = "inline-flex";
        btnPopupGoogleAuth.innerText = "🔐 Đăng nhập Google";
      }
    }
  }

  if (btnPopupGoogleAuth) {
    btnPopupGoogleAuth.addEventListener("click", async () => {
      btnPopupGoogleAuth.innerText = "⏳ Đang mở trình duyệt...";
      try {
        const res = await fetch(getApiUrl("/api/auth/google/start"), { method: "POST" });
        const data = await res.json();
        if (data.status === "ok" || data.status === "already_running") {
          appendBubble("ai", "🌐 Đã mở cửa sổ đăng nhập Google. Hãy đăng nhập tài khoản của bạn trên trình duyệt vừa xuất hiện!");
        }
      } catch (e) {
        btnPopupGoogleAuth.innerText = "🔐 Đăng nhập Google";
      }
    });
  }

  // Auto-focus input
  if (chatInput) {
    chatInput.focus();
  }

  // 1. Thinking Level Management
  function setThinkingLevelUI(level) {
    const lvl = (level || "medium").toLowerCase();
    currentThinkingLevel = ["low", "medium", "high"].includes(lvl) ? lvl : "medium";
    if (popupThinkingLevel) {
      popupThinkingLevel.value = currentThinkingLevel;
      const labelMap = {
        low: "Mức độ suy nghĩ: Thấp (Nhanh)",
        medium: "Mức độ suy nghĩ: Vừa (Mặc định)",
        high: "Mức độ suy nghĩ: Sâu (Chi tiết)"
      };
      popupThinkingLevel.setAttribute("aria-label", labelMap[currentThinkingLevel] || "Mức độ suy nghĩ AI");
    }
    try {
      localStorage.setItem("luga_thinking_level", currentThinkingLevel);
    } catch (e) {}
  }

  async function fetchThinkingLevel() {
    try {
      const res = await fetch("/api/thinking_level");
      const data = await res.json();
      if (data && data.thinking_level) {
        setThinkingLevelUI(data.thinking_level);
        return;
      }
    } catch (e) {}
    // Fallback to local storage or default 'medium'
    const saved = localStorage.getItem("luga_thinking_level") || "medium";
    setThinkingLevelUI(saved);
  }

  if (popupThinkingLevel) {
    popupThinkingLevel.addEventListener("change", async (e) => {
      const newLvl = e.target.value;
      setThinkingLevelUI(newLvl);
      try {
        await fetch("/api/thinking_level", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ thinking_level: newLvl })
        });
      } catch (err) {
        console.warn("[Popup] Could not sync thinking level:", err);
      }
    });
  }

  // 2. Clear Chat
  if (btnPopupClear) {
    btnPopupClear.addEventListener("click", async () => {
      if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: "CLEAR_CHAT" }));
      }
      try {
        await fetch("/api/clear_chat", { method: "POST" });
      } catch (e) {}
      if (chatThread) {
        chatThread.innerHTML = `
          <div class="popup-bubble ai" role="article" aria-label="Phản hồi từ Luga Assist">
            Đã xóa sạch lịch sử hội thoại. Bạn có thể nhập câu lệnh mới!
          </div>
        `;
      }
    });
  }

  // 3. WebSocket Connection
  function connectWebSocket() {
    const loc = window.location;
    const wsUrl = `ws://${loc.hostname || "127.0.0.1"}:${loc.port || "8765"}/ws/webui`;
    ws = new WebSocket(wsUrl);

    ws.onopen = () => {
      if (popupStatusDot) {
        popupStatusDot.style.background = "#10b981";
        popupStatusDot.setAttribute("title", "Máy chủ Luga đã kết nối");
        popupStatusDot.setAttribute("aria-label", "Trạng thái: Đã kết nối với máy chủ Luga");
      }
    };

    ws.onclose = () => {
      if (popupStatusDot) {
        popupStatusDot.style.background = "#ef4444";
        popupStatusDot.setAttribute("title", "Mất kết nối máy chủ, đang thử lại...");
        popupStatusDot.setAttribute("aria-label", "Trạng thái: Mất kết nối, đang tự động kết nối lại");
      }
      setTimeout(connectWebSocket, 2000);
    };

    ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data);
        handleMessage(msg);
      } catch (e) {}
    };
  }

  function handleMessage(msg) {
    if (msg.type === "GOOGLE_AUTH_SUCCESS") {
      updateGoogleStatus(true);
      appendBubble("ai", "🎉 Đăng nhập Google thành công! Gemini đã sẵn sàng.");
    } else if (msg.type === "MODE_CHANGED") {
      updateMode(msg.mode);
    } else if (msg.type === "STATUS_UPDATE") {
      if (msg.gemini_ready !== undefined) updateGoogleStatus(msg.gemini_ready);
      if (msg.mode) updateMode(msg.mode);
      if (msg.thinking_level) setThinkingLevelUI(msg.thinking_level);
    } else if (msg.type === "THINKING_LEVEL_CHANGED") {
      if (msg.thinking_level) setThinkingLevelUI(msg.thinking_level);
    } else if (msg.type === "ACTION_PROGRESS") {
      chatThinking.style.display = "flex";
      chatThinkingText.innerText = msg.message || "Đang phân tích màn hình...";
      chatThread.scrollTop = chatThread.scrollHeight;
    } else if (msg.type === "ACTION_COMPLETED" || msg.type === "ACTION_STEP") {
      chatThinking.style.display = "none";
      const speech = msg.speech || msg.action_result?.speech_result || "Hoàn thành";
      appendBubble("ai", speech);
    } else if (msg.type === "ERROR") {
      chatThinking.style.display = "none";
      appendBubble("ai", `⚠️ Lỗi: ${msg.message}`);
    } else if (msg.type === "CHAT_CLEARED") {
      if (chatThread) {
        chatThread.innerHTML = `
          <div class="popup-bubble ai" role="article" aria-label="Phản hồi từ Luga Assist">
            Đã xóa sạch lịch sử hội thoại.
          </div>
        `;
      }
    }
  }

  function appendBubble(sender, text) {
    const bubble = document.createElement("div");
    bubble.className = `popup-bubble ${sender}`;
    bubble.setAttribute("role", "article");
    const label = sender === "user" ? `Tin nhắn của bạn: ${text}` : `Phản hồi từ Luga Assist: ${text}`;
    bubble.setAttribute("aria-label", label);
    bubble.innerText = text;
    chatThread.appendChild(bubble);
    chatThread.scrollTop = chatThread.scrollHeight;
  }

  function updateMode(mode) {
    currentMode = mode === "chat" ? "chat" : "control";
    if (currentMode === "chat") {
      popupModeLabel.innerText = "💬 Trò chuyện AI";
      popupModeLabel.style.color = "#c084fc";
      if (btnPopupMode) {
        btnPopupMode.setAttribute("aria-label", "Chế độ hiện tại: Trò chuyện AI. Nhấn để chuyển sang Điều khiển PC");
      }
    } else {
      popupModeLabel.innerText = "🎮 Điều khiển PC";
      popupModeLabel.style.color = "#38bdf8";
      if (btnPopupMode) {
        btnPopupMode.setAttribute("aria-label", "Chế độ hiện tại: Điều khiển PC. Nhấn để chuyển sang Trò chuyện AI");
      }
    }
  }

  async function toggleMode() {
    const target = currentMode === "control" ? "chat" : "control";
    try {
      const res = await fetch("/api/set_mode", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ mode: target, announce: true })
      });
      const data = await res.json();
      if (data.mode) updateMode(data.mode);
    } catch (e) {}
  }

  // 4. Send Command with Thinking Level
  async function sendCommand(text) {
    text = (text || "").trim();
    if (!text) return;

    appendBubble("user", text);
    chatInput.value = "";
    chatThinking.style.display = "flex";
    chatThinkingText.innerText = "Luga đang xử lý câu lệnh...";

    const speak = chkTTS ? chkTTS.checked : true;
    const thinkingLevel = (popupThinkingLevel ? popupThinkingLevel.value : currentThinkingLevel) || "medium";

    try {
      const res = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          message: text,
          speak: speak,
          thinking_level: thinkingLevel
        })
      });
      const data = await res.json();
      chatThinking.style.display = "none";
      const reply = data.response || data.speech || "Thao tác đã thực hiện xong.";
      appendBubble("ai", reply);
    } catch (e) {
      chatThinking.style.display = "none";
      appendBubble("ai", `⚠️ Lỗi gửi lệnh: ${e.message}`);
    }
  }

  // 5. Web Speech API for Mic
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (SpeechRecognition) {
    recognition = new SpeechRecognition();
    recognition.lang = "vi-VN";
    recognition.continuous = false;
    recognition.interimResults = false;

    recognition.onstart = () => {
      isListening = true;
      btnMic.classList.add("listening");
      btnMic.setAttribute("aria-pressed", "true");
      btnMic.setAttribute("aria-label", "Đang ghi âm giọng nói... Nhấn để dừng");
      chatInput.placeholder = "Đang lắng nghe câu lệnh...";
    };

    recognition.onresult = (e) => {
      const transcript = e.results[0][0].transcript;
      if (transcript) {
        sendCommand(transcript);
      }
    };

    recognition.onend = () => {
      isListening = false;
      btnMic.classList.remove("listening");
      btnMic.setAttribute("aria-pressed", "false");
      btnMic.setAttribute("aria-label", "Bật micro để ra lệnh bằng giọng nói (F8)");
      chatInput.placeholder = "Nhập lệnh hoặc câu hỏi (Enter để gửi)...";
    };

    btnMic.addEventListener("click", () => {
      if (isListening) {
        recognition.stop();
      } else {
        recognition.start();
      }
    });
  } else {
    if (btnMic) {
      btnMic.style.display = "none";
    }
  }

  // 6. Form Submit & Key Controls
  chatForm.addEventListener("submit", (e) => {
    e.preventDefault();
    sendCommand(chatInput.value);
  });

  if (btnPopupMode) {
    btnPopupMode.addEventListener("click", toggleMode);
  }

  // Esc key closes popup window if opened as secondary window
  window.addEventListener("keydown", (e) => {
    if (e.code === "Escape") {
      window.close();
    }
  });

  // Init
  fetchThinkingLevel();
  connectWebSocket();
});
