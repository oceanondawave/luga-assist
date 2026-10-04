/**
 * Luga Assist - Mini Floating Popup Logic
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

  let ws = null;
  let currentMode = "control";
  let recognition = null;
  let isListening = false;

  // Auto-focus input
  if (chatInput) {
    chatInput.focus();
  }

  // 1. WebSocket
  function connectWebSocket() {
    const loc = window.location;
    const wsUrl = `ws://${loc.hostname || "127.0.0.1"}:${loc.port || "8000"}/ws/webui`;
    ws = new WebSocket(wsUrl);

    ws.onopen = () => {
      popupStatusDot.style.background = "#10b981";
    };

    ws.onclose = () => {
      popupStatusDot.style.background = "#ef4444";
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
    if (msg.type === "MODE_CHANGED") {
      updateMode(msg.mode);
    } else if (msg.type === "STATUS_UPDATE") {
      if (msg.mode) updateMode(msg.mode);
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
    }
  }

  function appendBubble(sender, text) {
    const bubble = document.createElement("div");
    bubble.className = `popup-bubble ${sender}`;
    bubble.innerText = text;
    chatThread.appendChild(bubble);
    chatThread.scrollTop = chatThread.scrollHeight;
  }

  function updateMode(mode) {
    currentMode = mode === "chat" ? "chat" : "control";
    if (currentMode === "chat") {
      popupModeLabel.innerText = "💬 Trò chuyện AI";
      popupModeLabel.style.color = "#c084fc";
    } else {
      popupModeLabel.innerText = "🎮 Điều khiển PC";
      popupModeLabel.style.color = "#38bdf8";
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

  // 2. Send Command
  async function sendCommand(text) {
    text = (text || "").trim();
    if (!text) return;

    appendBubble("user", text);
    chatInput.value = "";
    chatThinking.style.display = "flex";
    chatThinkingText.innerText = "Luga đang xử lý câu lệnh...";

    const speak = chkTTS ? chkTTS.checked : true;

    try {
      const res = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: text, speak: speak })
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

  // 3. Web Speech API for Mic
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (SpeechRecognition) {
    recognition = new SpeechRecognition();
    recognition.lang = "vi-VN";
    recognition.continuous = false;
    recognition.interimResults = false;

    recognition.onstart = () => {
      isListening = true;
      btnMic.classList.add("listening");
      chatInput.placeholder = "Đang lắng nghe...";
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
    if (btnMic) btnMic.style.display = "none";
  }

  // 4. Form Submit
  chatForm.addEventListener("submit", (e) => {
    e.preventDefault();
    sendCommand(chatInput.value);
  });

  if (btnPopupMode) {
    btnPopupMode.addEventListener("click", toggleMode);
  }

  // Esc key closes popup window if opened via window.open
  window.addEventListener("keydown", (e) => {
    if (e.code === "Escape") {
      window.close();
    }
  });

  // Init
  connectWebSocket();
});
