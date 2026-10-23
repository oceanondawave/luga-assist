/**
 * Luga Assist - Web Spotlight Controller
 * Fully accessible with NVDA screen reader (100% ARIA compliant)
 * Direct Google Web Login without Chrome Extension or API Keys
 */
document.addEventListener("DOMContentLoaded", () => {
  const spotlightThread = document.getElementById("spotlightThread");
  const spotlightThinking = document.getElementById("spotlightThinking");
  const spotlightThinkingText = document.getElementById("spotlightThinkingText");
  const spotlightForm = document.getElementById("spotlightForm");
  const spotlightInput = document.getElementById("spotlightInput");
  const btnMic = document.getElementById("btnSpotlightMic");
  const chkTTS = document.getElementById("chkSpotlightTTS");
  const btnGoogleAuth = document.getElementById("btnGoogleAuth");
  const googleAuthText = document.getElementById("googleAuthText");
  const spotlightThinkingLevel = document.getElementById("spotlightThinkingLevel");
  const btnSpotlightMode = document.getElementById("btnSpotlightMode");
  const spotlightModeLabel = document.getElementById("spotlightModeLabel");
  const btnSpotlightClear = document.getElementById("btnSpotlightClear");
  const btnSpotlightClose = document.getElementById("btnSpotlightClose");

  let ws = null;
  let currentMode = "control";
  let currentThinkingLevel = "medium";
  let geminiReady = false;
  let recognition = null;
  let isListening = false;

  // Auto-focus input on open
  if (spotlightInput) {
    spotlightInput.focus();
  }

  // 1. Google Web Login Management (No Extension, No API Key, Pure Web Sign-in)
  function updateGoogleAuthUI(isReady) {
    geminiReady = isReady;
    if (btnGoogleAuth) {
      if (isReady) {
        btnGoogleAuth.className = "spotlight-auth-btn online";
        btnGoogleAuth.classList.remove("pulse");
        btnGoogleAuth.setAttribute("aria-label", "Google Gemini: Đã kết nối thành công. Nhấn để đăng nhập lại nếu muốn");
        btnGoogleAuth.setAttribute("title", "Google Gemini đã sẵn sàng");
        btnGoogleAuth.innerHTML = '<span aria-hidden="true">🟢</span> <span>Google: Đã kết nối</span>';
      } else {
        btnGoogleAuth.className = "spotlight-auth-btn offline pulse";
        btnGoogleAuth.setAttribute("aria-label", "Google Gemini: Chưa đăng nhập. Nhấn để đăng nhập tài khoản Google trên web");
        btnGoogleAuth.setAttribute("title", "Nhấn để đăng nhập tài khoản Google");
        btnGoogleAuth.innerHTML = '<span aria-hidden="true">🔐</span> <span>Đăng nhập Google</span>';
      }
    }
  }

  async function checkGoogleStatus() {
    try {
      const res = await fetch("/api/status");
      const data = await res.json();
      updateGoogleAuthUI(Boolean(data.gemini_ready));
    } catch (e) {
      updateGoogleAuthUI(false);
    }
  }

  if (btnGoogleAuth) {
    btnGoogleAuth.addEventListener("click", async () => {
      btnGoogleAuth.innerHTML = '<span aria-hidden="true">⏳</span> <span>Đang mở trình duyệt...</span>';
      btnGoogleAuth.setAttribute("aria-label", "Đang mở cửa sổ đăng nhập Google trên trình duyệt. Vui lòng đăng nhập tài khoản của bạn.");

      try {
        const res = await fetch("/api/auth/google/start", { method: "POST" });
        const data = await res.json();
        if (data.status === "ok" || data.status === "already_running") {
          appendBubble("ai", "🌐 Đã mở cửa sổ đăng nhập Google. Hãy đăng nhập tài khoản của bạn trên trình duyệt vừa xuất hiện. Luga sẽ tự động kết nối ngay khi bạn đăng nhập xong!");
        } else {
          appendBubble("ai", `⚠️ ${data.message || "Không thể khởi chạy cửa sổ đăng nhập."}`);
          updateGoogleAuthUI(false);
        }
      } catch (err) {
        appendBubble("ai", `⚠️ Lỗi kết nối máy chủ: ${err.message}`);
        updateGoogleAuthUI(false);
      }
    });
  }

  // 2. Thinking Level Management
  function setThinkingLevelUI(level) {
    const lvl = (level || "medium").toLowerCase();
    currentThinkingLevel = ["low", "medium", "high"].includes(lvl) ? lvl : "medium";
    if (spotlightThinkingLevel) {
      spotlightThinkingLevel.value = currentThinkingLevel;
      const labelMap = {
        low: "Mức độ suy nghĩ: Thấp (Nhanh, phản hồi ngay)",
        medium: "Mức độ suy nghĩ: Vừa (Mặc định, cân bằng tốc độ & độ chuẩn)",
        high: "Mức độ suy nghĩ: Sâu (Chi tiết, phân tích đa bước)"
      };
      spotlightThinkingLevel.setAttribute("aria-label", labelMap[currentThinkingLevel] || "Mức độ suy nghĩ AI");
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
    const saved = localStorage.getItem("luga_thinking_level") || "medium";
    setThinkingLevelUI(saved);
  }

  if (spotlightThinkingLevel) {
    spotlightThinkingLevel.addEventListener("change", async (e) => {
      const newLvl = e.target.value;
      setThinkingLevelUI(newLvl);
      try {
        await fetch("/api/thinking_level", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ thinking_level: newLvl })
        });
      } catch (err) {}
    });
  }

  // 3. Clear Chat
  if (btnSpotlightClear) {
    btnSpotlightClear.addEventListener("click", async () => {
      if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: "CLEAR_CHAT" }));
      }
      try {
        await fetch("/api/clear_chat", { method: "POST" });
      } catch (e) {}
      if (spotlightThread) {
        spotlightThread.innerHTML = `
          <div class="spotlight-bubble ai" role="article" aria-label="Phản hồi từ Luga Spotlight">
            Đã xóa sạch nội dung. Bạn có thể gõ câu lệnh hoặc ấn F8 để nói!
          </div>
        `;
      }
    });
  }

  // 4. WebSocket Connection
  function connectWebSocket() {
    const loc = window.location;
    const wsUrl = `ws://${loc.hostname || "127.0.0.1"}:${loc.port || "8765"}/ws/webui`;
    ws = new WebSocket(wsUrl);

    ws.onopen = () => {
      checkGoogleStatus();
    };

    ws.onclose = () => {
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
      updateGoogleAuthUI(true);
      appendBubble("ai", "🎉 Đăng nhập Google thành công! Kết nối Gemini đã sẵn sàng. Bạn có thể điều khiển máy tính ngay bây giờ!");
    } else if (msg.type === "STATUS_UPDATE") {
      if (msg.gemini_ready !== undefined) {
        updateGoogleAuthUI(msg.gemini_ready);
      }
      if (msg.mode) updateMode(msg.mode);
      if (msg.thinking_level) setThinkingLevelUI(msg.thinking_level);
    } else if (msg.type === "MODE_CHANGED") {
      updateMode(msg.mode);
    } else if (msg.type === "THINKING_LEVEL_CHANGED") {
      if (msg.thinking_level) setThinkingLevelUI(msg.thinking_level);
    } else if (msg.type === "ACTION_PROGRESS") {
      spotlightThinking.style.display = "flex";
      spotlightThinkingText.innerText = msg.message || "Đang phân tích màn hình...";
      spotlightThread.scrollTop = spotlightThread.scrollHeight;
    } else if (msg.type === "ACTION_COMPLETED" || msg.type === "ACTION_STEP") {
      spotlightThinking.style.display = "none";
      const speech = msg.speech || msg.action_result?.speech_result || "Hoàn thành";
      appendBubble("ai", speech);
    } else if (msg.type === "ERROR") {
      spotlightThinking.style.display = "none";
      appendBubble("ai", `⚠️ Lỗi: ${msg.message}`);
    } else if (msg.type === "CHAT_CLEARED") {
      if (spotlightThread) {
        spotlightThread.innerHTML = `
          <div class="spotlight-bubble ai" role="article" aria-label="Phản hồi từ Luga Spotlight">
            Đã làm mới cuộc trò chuyện.
          </div>
        `;
      }
    } else if (msg.type === "SPOTLIGHT_TOGGLE") {
      // Toggle spotlight focus or visibility
      if (document.hasFocus()) {
        window.close();
      } else {
        window.focus();
        if (spotlightInput) spotlightInput.focus();
      }
    }
  }

  function appendBubble(sender, text) {
    const bubble = document.createElement("div");
    bubble.className = `spotlight-bubble ${sender}`;
    bubble.setAttribute("role", "article");
    const label = sender === "user" ? `Bạn đã gửi: ${text}` : `Luga trả lời: ${text}`;
    bubble.setAttribute("aria-label", label);
    bubble.innerText = text;
    spotlightThread.appendChild(bubble);
    spotlightThread.scrollTop = spotlightThread.scrollHeight;
  }

  function updateMode(mode) {
    currentMode = mode === "chat" ? "chat" : "control";
    if (currentMode === "chat") {
      spotlightModeLabel.innerText = "💬 Trò chuyện AI";
      spotlightModeLabel.style.color = "#c084fc";
      if (btnSpotlightMode) {
        btnSpotlightMode.setAttribute("aria-label", "Chế độ hiện tại: Trò chuyện AI. Nhấn để chuyển sang Điều khiển PC");
      }
    } else {
      spotlightModeLabel.innerText = "🎮 Điều khiển PC";
      spotlightModeLabel.style.color = "#38bdf8";
      if (btnSpotlightMode) {
        btnSpotlightMode.setAttribute("aria-label", "Chế độ hiện tại: Điều khiển PC. Nhấn để chuyển sang Trò chuyện AI");
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

  // 5. Send Command
  async function sendCommand(text) {
    text = (text || "").trim();
    if (!text) return;

    appendBubble("user", text);
    spotlightInput.value = "";
    spotlightThinking.style.display = "flex";
    spotlightThinkingText.innerText = "Luga đang chụp màn hình và phân tích...";

    const speak = chkTTS ? chkTTS.checked : true;
    const thinkingLevel = (spotlightThinkingLevel ? spotlightThinkingLevel.value : currentThinkingLevel) || "medium";

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
      spotlightThinking.style.display = "none";
      const reply = data.response || data.speech || "Thao tác đã thực hiện xong.";
      appendBubble("ai", reply);
    } catch (e) {
      spotlightThinking.style.display = "none";
      appendBubble("ai", `⚠️ Lỗi gửi lệnh: ${e.message}`);
    }
  }

  // 6. Web Speech API for Mic
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
      spotlightInput.placeholder = "Đang lắng nghe câu lệnh...";
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
      btnMic.setAttribute("aria-label", "Nói qua Micro (F8)");
      spotlightInput.placeholder = "Nhập lệnh hoặc câu hỏi (Enter gửi, Esc ẩn)...";
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
      btnMic.addEventListener("click", () => {
        appendBubble("ai", "💡 Nhấn phím F8 từ bất kỳ đâu trên bàn phím để kích hoạt nhận diện giọng nói Luga Assist!");
      });
    }
  }

  // 7. Form Submit & Key Controls
  spotlightForm.addEventListener("submit", (e) => {
    e.preventDefault();
    sendCommand(spotlightInput.value);
  });

  if (btnSpotlightMode) {
    btnSpotlightMode.addEventListener("click", toggleMode);
  }

  if (btnSpotlightClose) {
    btnSpotlightClose.addEventListener("click", () => {
      window.close();
    });
  }

  // Escape key closes/hides the Spotlight window
  window.addEventListener("keydown", (e) => {
    if (e.code === "Escape") {
      window.close();
    }
  });

  // Init
  fetchThinkingLevel();
  connectWebSocket();
  checkGoogleStatus();
});
