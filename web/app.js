/**
 * Luga Assist - Web Interface Logic
 * Supports Computer Control Mode & Conversational AI Chat Mode.
 * Handles Web Speech API (Vietnamese), WebSockets, Sound Earcons, and Accessible Hotkeys.
 */

document.addEventListener("DOMContentLoaded", () => {
  // DOM Elements - Header & Status
  const tabBtnControl = document.getElementById("tabBtnControl");
  const tabBtnChat = document.getElementById("tabBtnChat");
  const panelControl = document.getElementById("panelControl");
  const panelChat = document.getElementById("panelChat");
  const agentDot = document.getElementById("agentDot");
  const agentStatusText = document.getElementById("agentStatusText");
  const extDot = document.getElementById("extDot");
  const extStatusText = document.getElementById("extStatusText");

  // DOM Elements - Control Mode
  const btnMic = document.getElementById("btnMic");
  const speechDisplay = document.getElementById("speechDisplay");
  const activityLog = document.getElementById("activityLog");
  const previewPlaceholder = document.getElementById("previewPlaceholder");
  const lastActionImg = document.getElementById("lastActionImg");
  const selectVoice = document.getElementById("selectVoice");
  const btnReadScreen = document.getElementById("btnReadScreen");

  // DOM Elements - Chat Mode
  const chatThread = document.getElementById("chatThread");
  const chatThinking = document.getElementById("chatThinking");
  const chatForm = document.getElementById("chatForm");
  const chatInput = document.getElementById("chatInput");
  const btnChatMic = document.getElementById("btnChatMic");
  const btnChatClear = document.getElementById("btnChatClear");
  const chkChatTTS = document.getElementById("chkChatTTS");

  let ws = null;
  let isListening = false;
  let isChatListening = false;
  let recognition = null;
  let audioCtx = null;
  let continuousMode = false;
  let currentMode = "control"; // "control" or "chat"

  // Initialize Web Audio API for Earcons
  function getAudioContext() {
    if (!audioCtx) {
      audioCtx = new (window.AudioContext || window.webkitAudioContext)();
    }
    return audioCtx;
  }

  function playTone(freq, type = "sine", duration = 0.15) {
    try {
      const ctx = getAudioContext();
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.type = type;
      osc.frequency.setValueAtTime(freq, ctx.currentTime);
      gain.gain.setValueAtTime(0.15, ctx.currentTime);
      gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + duration);
      osc.connect(gain);
      gain.connect(ctx.destination);
      osc.start();
      osc.stop(ctx.currentTime + duration);
    } catch (e) {}
  }

  function soundStartListening() {
    playTone(587, "sine", 0.1);
    setTimeout(() => playTone(880, "sine", 0.15), 100);
  }

  function soundStopListening() {
    playTone(880, "sine", 0.1);
    setTimeout(() => playTone(587, "sine", 0.15), 100);
  }

  function soundSuccess() {
    playTone(523.25, "triangle", 0.12);
    setTimeout(() => playTone(659.25, "triangle", 0.15), 100);
  }

  function soundError() {
    playTone(220, "sawtooth", 0.25);
  }

  // 1. Mode Switch Handler
  function switchMode(newMode, notifyServer = true) {
    if (newMode !== "control" && newMode !== "chat") return;
    currentMode = newMode;

    if (currentMode === "control") {
      tabBtnControl.classList.add("active");
      tabBtnControl.setAttribute("aria-selected", "true");
      tabBtnChat.classList.remove("active");
      tabBtnChat.setAttribute("aria-selected", "false");

      panelControl.style.display = "grid";
      panelChat.style.display = "none";
    } else {
      tabBtnChat.classList.add("active");
      tabBtnChat.setAttribute("aria-selected", "true");
      tabBtnControl.classList.remove("active");
      tabBtnControl.setAttribute("aria-selected", "false");

      panelControl.style.display = "none";
      panelChat.style.display = "flex";
      chatInput?.focus();
    }

    if (notifyServer && ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({
        type: "SWITCH_MODE",
        mode: currentMode,
        announce: true,
      }));
    }
  }

  tabBtnControl.addEventListener("click", () => switchMode("control"));
  tabBtnChat.addEventListener("click", () => switchMode("chat"));

  // 2. Web Speech API for Vietnamese
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;

  if (SpeechRecognition) {
    recognition = new SpeechRecognition();
    recognition.lang = "vi-VN";
    recognition.continuous = false;
    recognition.interimResults = true;
    recognition.maxAlternatives = 1;

    recognition.onstart = () => {
      isListening = true;
      if (isChatListening) {
        btnChatMic.classList.add("listening");
        chatInput.placeholder = "Đang lắng nghe giọng nói của bạn...";
      } else {
        btnMic.classList.add("listening");
        speechDisplay.innerText = "Đang lắng nghe giọng nói của bạn...";
        speechDisplay.style.borderColor = "var(--accent-red)";
      }
      soundStartListening();
    };

    recognition.onresult = (event) => {
      let interimTranscript = "";
      let finalTranscript = "";

      for (let i = event.resultIndex; i < event.results.length; ++i) {
        if (event.results[i].isFinal) {
          finalTranscript += event.results[i][0].transcript;
        } else {
          interimTranscript += event.results[i][0].transcript;
        }
      }

      if (isChatListening) {
        if (interimTranscript) chatInput.value = interimTranscript;
        if (finalTranscript) {
          chatInput.value = finalTranscript.trim();
          sendChatMessage(finalTranscript.trim());
        }
      } else {
        if (interimTranscript) speechDisplay.innerText = interimTranscript;
        if (finalTranscript) {
          finalTranscript = finalTranscript.trim();
          speechDisplay.innerText = `"${finalTranscript}"`;
          sendVoiceCommand(finalTranscript);
        }
      }
    };

    recognition.onerror = (event) => {
      console.warn("[SpeechRecognition] Error:", event.error);
      if (event.error !== "no-speech") {
        if (isChatListening) {
          chatInput.placeholder = `Lỗi nhận diện: ${event.error}`;
        } else {
          speechDisplay.innerText = `Lỗi nhận diện âm thanh: ${event.error}`;
        }
        soundError();
      }
      stopListening();
    };

    recognition.onend = () => {
      stopListening();
      if (continuousMode && currentMode === "control") {
        setTimeout(startListening, 1000);
      }
    };
  } else {
    speechDisplay.innerText = "Trình duyệt không hỗ trợ Web Speech API. Vui lòng mở trên Google Chrome.";
  }

  function startListening(forChat = false) {
    if (!recognition || isListening) return;
    isChatListening = forChat;
    try {
      recognition.start();
    } catch (e) {
      console.warn("Could not start recognition:", e);
    }
  }

  function stopListening() {
    isListening = false;
    btnMic.classList.remove("listening");
    btnChatMic.classList.remove("listening");
    speechDisplay.style.borderColor = "var(--border)";
    chatInput.placeholder = "Nhập câu hỏi hoặc nhấn nút Micro bên phải để nói...";
    soundStopListening();
  }

  btnMic.addEventListener("click", () => {
    if (isListening) {
      recognition.stop();
      stopListening();
    } else {
      startListening(false);
    }
  });

  btnChatMic.addEventListener("click", () => {
    if (isListening) {
      recognition.stop();
      stopListening();
    } else {
      startListening(true);
    }
  });

  // 3. Connect WebSocket to Local Agent
  function connectWebSocket() {
    const loc = window.location;
    const wsUrl = `ws://${loc.hostname || "127.0.0.1"}:${loc.port || "8000"}/ws/webui`;

    ws = new WebSocket(wsUrl);

    ws.onopen = () => {
      agentDot.classList.add("online");
      agentStatusText.innerText = "Local Agent: Đã kết nối (Cổng 8000)";
      console.log("[Luga Assist] WebUI WebSocket connected.");
    };

    ws.onclose = () => {
      agentDot.classList.remove("online");
      agentStatusText.innerText = "Local Agent: Mất kết nối (Đang thử lại...)";
      setTimeout(connectWebSocket, 2000);
    };

    ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data);
        handleServerMessage(msg);
      } catch (e) {
        console.error("Failed to parse server message:", e);
      }
    };
  }

  function handleServerMessage(msg) {
    // Mode Changed Notification
    if (msg.type === "MODE_CHANGED") {
      switchMode(msg.mode, false);
      return;
    }

    if (msg.type === "STATUS_UPDATE") {
      if (msg.gemini_ready || msg.extension_connected) {
        extDot.classList.add("online");
        extStatusText.innerText = "Google Gemini: Đã sẵn sàng (Chạy ngầm)";
      } else {
        extDot.classList.remove("online");
        extStatusText.innerText = "Google Gemini: Đang chờ Extension";
      }

      if (msg.mode && msg.mode !== currentMode) {
        switchMode(msg.mode, false);
      }
    } else if (msg.type === "ACTION_PROGRESS") {
      speechDisplay.innerText = msg.message;
    } else if (msg.type === "ACTION_COMPLETED") {
      speechDisplay.innerText = msg.speech || "Đã hoàn thành thao tác.";
      soundSuccess();
      appendLog(msg.user_command, msg.speech, msg.action_result);

      if (msg.annotated_image) {
        lastActionImg.src = msg.annotated_image;
        lastActionImg.style.display = "block";
        previewPlaceholder.style.display = "none";
      }
    } else if (msg.type === "CHAT_PROGRESS") {
      chatThinking.style.display = "flex";
      chatThread.scrollTop = chatThread.scrollHeight;
    } else if (msg.type === "CHAT_RESPONSE") {
      chatThinking.style.display = "none";
      appendChatBubble("ai", msg.response);
      soundSuccess();
    } else if (msg.type === "CHAT_CLEARED") {
      chatThread.innerHTML = `
        <div class="chat-bubble ai">
          <div class="chat-avatar" aria-hidden="true">🤖</div>
          <div class="chat-content">
            <div class="chat-sender">Gemini Assistant</div>
            <div class="chat-text">✨ Phiên trò chuyện đã được làm mới. Hãy đặt câu hỏi bất kỳ cho tôi nhé!</div>
          </div>
        </div>
      `;
    } else if (msg.type === "ERROR") {
      chatThinking.style.display = "none";
      speechDisplay.innerText = `Lỗi: ${msg.message}`;
      soundError();
      if (currentMode === "control") {
        appendLog(msg.user_command || "Thao tác", msg.message, { success: false });
      } else {
        appendChatBubble("ai", `⚠️ Lỗi: ${msg.message}`);
      }
    }
  }

  // 4. Send Commands & Chat Messages
  function sendVoiceCommand(text) {
    if (!ws || ws.readyState !== WebSocket.OPEN) {
      speechDisplay.innerText = "Chưa kết nối tới Local Agent. Hãy chắc chắn server đang chạy!";
      soundError();
      return;
    }

    speechDisplay.innerText = `Đang gửi lệnh: "${text}"...`;

    ws.send(
      JSON.stringify({
        type: "VOICE_COMMAND",
        command: text,
        voice: selectVoice.value,
      })
    );
  }

  function sendChatMessage(text) {
    if (!text) return;
    if (!ws || ws.readyState !== WebSocket.OPEN) {
      appendChatBubble("ai", "⚠️ Chưa kết nối tới Local Agent. Vui lòng kiểm tra lại server.");
      soundError();
      return;
    }

    appendChatBubble("user", text);
    chatInput.value = "";
    chatThinking.style.display = "flex";
    chatThread.scrollTop = chatThread.scrollHeight;

    ws.send(
      JSON.stringify({
        type: "CHAT_MESSAGE",
        message: text,
        voice: selectVoice.value,
        speak: chkChatTTS.checked,
      })
    );
  }

  function appendChatBubble(sender, text) {
    const bubble = document.createElement("div");
    bubble.className = `chat-bubble ${sender}`;

    const isAI = sender === "ai";
    const avatar = isAI ? "🤖" : "🗣️";
    const senderName = isAI ? "Gemini Assistant" : "Bạn";

    // Escape HTML but preserve basic breaks
    const escaped = text
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/\n/g, "<br>");

    let actionButton = "";
    if (isAI) {
      actionButton = `
        <button class="btn-speak-again" onclick="window.speakAgain('${encodeURIComponent(text)}')">
          🔊 Nghe lại
        </button>
      `;
    }

    bubble.innerHTML = `
      <div class="chat-avatar" aria-hidden="true">${avatar}</div>
      <div class="chat-content">
        <div class="chat-sender">${senderName}</div>
        <div class="chat-text">${escaped}</div>
        ${actionButton}
      </div>
    `;

    chatThread.appendChild(bubble);
    chatThread.scrollTop = chatThread.scrollHeight;
  }

  window.speakAgain = function (encodedText) {
    const text = decodeURIComponent(encodedText);
    fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: text, speak: true }),
    }).catch(console.error);
  };

  chatForm.addEventListener("submit", (e) => {
    e.preventDefault();
    const val = chatInput.value.trim();
    if (val) sendChatMessage(val);
  });

  btnChatClear.addEventListener("click", () => {
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: "CLEAR_CHAT" }));
    }
  });

  function appendLog(userCmd, aiReply, actionResult) {
    const item = document.createElement("div");
    const isSuccess = actionResult?.success !== false;
    item.className = `log-item ${isSuccess ? "success" : "error"}`;

    item.innerHTML = `
      <div class="log-user">🗣️ "${userCmd}"</div>
      <div class="log-reply">🤖 ${aiReply}</div>
      <div class="log-action">⚡ Chi tiết: ${actionResult?.details || actionResult?.action || "Hoàn thành"}</div>
    `;

    activityLog.insertBefore(item, activityLog.firstChild);
  }

  // 5. Accessible Hotkeys Handlers
  window.addEventListener("keydown", (e) => {
    // F9: Toggle between Computer Control and Chat Mode
    if (e.code === "F9") {
      e.preventDefault();
      const nextMode = currentMode === "control" ? "chat" : "control";
      switchMode(nextMode, true);
      return;
    }

    // Escape: Cancel listening or speech
    if (e.code === "Escape") {
      e.preventDefault();
      if (isListening) stopListening();
      if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: "STOP_SPEECH" }));
      }
      return;
    }

    // Ignore other keys if user is typing in input fields
    if (e.target.tagName === "INPUT" || e.target.tagName === "SELECT" || e.target.tagName === "TEXTAREA") return;

    if (e.code === "Space" && !e.repeat) {
      e.preventDefault();
      if (!isListening) startListening(currentMode === "chat");
    } else if (e.code === "F2") {
      e.preventDefault();
      continuousMode = !continuousMode;
      speechDisplay.innerText = continuousMode ? "Đã bật chế độ nghe liên tục (F2)" : "Đã tắt chế độ nghe liên tục (F2)";
    } else if (e.code === "F4") {
      e.preventDefault();
      triggerReadScreen();
    }
  });

  window.addEventListener("keyup", (e) => {
    if (e.code === "Space" && isListening && !continuousMode) {
      if (e.target.tagName === "INPUT" || e.target.tagName === "TEXTAREA") return;
      e.preventDefault();
      setTimeout(() => {
        if (recognition && isListening) recognition.stop();
      }, 500);
    }
  });

  function triggerReadScreen() {
    sendVoiceCommand("Hãy miêu tả chi tiết những gì đang hiển thị trên màn hình máy tính của tôi.");
  }

  btnReadScreen.addEventListener("click", triggerReadScreen);

  // Initialize
  connectWebSocket();
});
