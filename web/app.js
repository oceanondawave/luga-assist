/**
 * Luga Assist - Web Interface Logic
 * Interactive Chat & Voice Command Center for PC Control.
 */

document.addEventListener("DOMContentLoaded", () => {
  // DOM Elements - Status
  const agentDot = document.getElementById("agentDot");
  const agentStatusText = document.getElementById("agentStatusText");
  const extDot = document.getElementById("extDot");
  const extStatusText = document.getElementById("extStatusText");

  // DOM Elements - Chat Hub
  const chatThread = document.getElementById("chatThread");
  const chatThinking = document.getElementById("chatThinking");
  const chatThinkingText = document.getElementById("chatThinkingText");
  const chatForm = document.getElementById("chatForm");
  const chatInput = document.getElementById("chatInput");
  const btnMic = document.getElementById("btnMic");
  const btnChatClear = document.getElementById("btnChatClear");
  const chkTTS = document.getElementById("chkTTS");
  const selectVoice = document.getElementById("selectVoice");

  // DOM Elements - Monitor Panel
  const activityLog = document.getElementById("activityLog");
  const previewPlaceholder = document.getElementById("previewPlaceholder");
  const lastActionImg = document.getElementById("lastActionImg");
  const btnReadScreen = document.getElementById("btnReadScreen");

  // DOM Elements - Header actions
  const btnSystemStatus = document.getElementById("btnSystemStatus");
  const btnToggleMode = document.getElementById("btnToggleMode");
  const btnHeaderShutdown = document.getElementById("btnHeaderShutdown");
  const modeIcon = document.getElementById("modeIcon");
  const modeLabel = document.getElementById("modeLabel");

  // DOM Elements - Modals
  const statusModal = document.getElementById("statusModal");
  const btnCloseStatusModal = document.getElementById("btnCloseStatusModal");
  const modalServerStatus = document.getElementById("modalServerStatus");
  const modalCurrentMode = document.getElementById("modalCurrentMode");
  const btnModalSwitchMode = document.getElementById("btnModalSwitchMode");
  const modalGeminiStatus = document.getElementById("modalGeminiStatus");
  const modalScreenRes = document.getElementById("modalScreenRes");
  const modalPid = document.getElementById("modalPid");
  const btnTestVoice = document.getElementById("btnTestVoice");
  const btnModalRestart = document.getElementById("btnModalRestart");
  const btnModalShutdown = document.getElementById("btnModalShutdown");

  const shutdownModal = document.getElementById("shutdownModal");
  const btnCloseShutdownModal = document.getElementById("btnCloseShutdownModal");
  const btnCancelShutdown = document.getElementById("btnCancelShutdown");
  const btnConfirmShutdown = document.getElementById("btnConfirmShutdown");

  let currentOperatingMode = "control";
  let ws = null;
  let isListening = false;
  let recognition = null;
  let audioCtx = null;
  let lastUserCommandRendered = "";

  // Web Audio Earcons
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

  // 1. Web Speech API for Vietnamese
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;

  if (SpeechRecognition) {
    recognition = new SpeechRecognition();
    recognition.lang = "vi-VN";
    recognition.continuous = false;
    recognition.interimResults = true;
    recognition.maxAlternatives = 1;

    recognition.onstart = () => {
      isListening = true;
      btnMic.classList.add("listening");
      chatInput.placeholder = "Đang lắng nghe giọng nói của bạn...";
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

      if (interimTranscript) {
        chatInput.value = interimTranscript;
      }

      if (finalTranscript) {
        chatInput.value = finalTranscript.trim();
        sendCommand(finalTranscript.trim());
      }
    };

    recognition.onerror = (event) => {
      console.warn("[SpeechRecognition] Error:", event.error);
      if (event.error !== "no-speech") {
        chatInput.placeholder = `Lỗi nhận diện: ${event.error}`;
        soundError();
      }
      stopListening();
    };

    recognition.onend = () => {
      stopListening();
    };
  } else {
    chatInput.placeholder = "Trình duyệt không hỗ trợ Web Speech API. Bạn có thể gõ phím trực tiếp.";
  }

  function startListening() {
    if (!recognition || isListening) return;
    try {
      recognition.start();
    } catch (e) {
      console.warn("Could not start recognition:", e);
    }
  }

  function stopListening() {
    isListening = false;
    btnMic.classList.remove("listening");
    chatInput.placeholder = "Nhập lệnh điều khiển hệ thống (VD: mở Spotify, tắt tiếng, tìm file, mô tả màn hình...)...";
    soundStopListening();
  }

  btnMic.addEventListener("click", () => {
    if (isListening) {
      recognition.stop();
      stopListening();
    } else {
      startListening();
    }
  });

  // 2. WebSocket Connection
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
    if (msg.type === "STATUS_UPDATE") {
      if (msg.gemini_ready || msg.extension_connected) {
        extDot.classList.add("online");
        extStatusText.innerText = "Google Gemini: Đã sẵn sàng (Chạy ngầm)";
      } else {
        extDot.classList.remove("online");
        extStatusText.innerText = "Google Gemini: Đang chờ kết nối";
      }
      if (msg.mode) {
        updateModeUI(msg.mode);
      }
    } else if (msg.type === "MODE_CHANGED") {
      updateModeUI(msg.mode);
    } else if (msg.type === "USER_CHAT_MESSAGE") {
      const text = msg.command || msg.text;
      if (text && text !== lastUserCommandRendered) {
        appendChatBubble("user", text);
        lastUserCommandRendered = text;
      }
      chatThinking.style.display = "flex";
      chatThinkingText.innerText = "Luga đang chụp màn hình và phân tích...";
      chatThread.scrollTop = chatThread.scrollHeight;
    } else if (msg.type === "ACTION_PROGRESS") {
      chatThinking.style.display = "flex";
      chatThinkingText.innerText = msg.message || "Đang phân tích màn hình...";
      chatThread.scrollTop = chatThread.scrollHeight;
    } else if (msg.type === "ACTION_STEP" || msg.type === "ACTION_COMPLETED") {
      chatThinking.style.display = "none";
      soundSuccess();

      // Ensure user bubble exists if triggered externally (e.g. from F8 hotkey)
      if (msg.user_command && msg.user_command !== lastUserCommandRendered) {
        appendChatBubble("user", msg.user_command);
        lastUserCommandRendered = msg.user_command;
      }

      // Append Assistant bubble in chat thread
      appendAssistantBubble(msg);

      // Update right monitor panel
      if (msg.annotated_image) {
        lastActionImg.src = msg.annotated_image;
        lastActionImg.style.display = "block";
        previewPlaceholder.style.display = "none";
      }

      appendLog(msg.user_command, msg.speech, msg.action_result);
    } else if (msg.type === "CHAT_CLEARED") {
      chatThread.innerHTML = `
        <div class="chat-bubble ai">
          <div class="chat-avatar" aria-hidden="true">🤖</div>
          <div class="chat-content">
            <div class="chat-sender">Luga Assist</div>
            <div class="chat-text">✨ Phiên làm việc đã được làm mới. Hãy nhập hoặc nói câu lệnh bất kỳ để điều khiển máy tính nhé!</div>
          </div>
        </div>
      `;
      activityLog.innerHTML = "";
    } else if (msg.type === "ERROR") {
      chatThinking.style.display = "none";
      soundError();
      appendChatBubble("ai", `⚠️ Lỗi: ${msg.message}`);
      appendLog(msg.user_command || "Thao tác", msg.message, { success: false });
    }
  }

  // 3. Command Sending (Chat & Voice)
  function sendCommand(text) {
    text = (text || "").trim();
    if (!text) return;

    if (!ws || ws.readyState !== WebSocket.OPEN) {
      appendChatBubble("ai", "⚠️ Chưa kết nối tới Local Agent. Hãy đảm bảo server Luga đang chạy.");
      soundError();
      return;
    }

    appendChatBubble("user", text);
    lastUserCommandRendered = text;
    chatInput.value = "";
    chatThinking.style.display = "flex";
    chatThinkingText.innerText = "Luga đang chụp màn hình và phân tích...";
    chatThread.scrollTop = chatThread.scrollHeight;

    ws.send(
      JSON.stringify({
        type: "TEXT_COMMAND",
        command: text,
        voice: selectVoice.value,
        speak: chkTTS.checked,
      })
    );
  }

  function appendChatBubble(sender, text) {
    const bubble = document.createElement("div");
    bubble.className = `chat-bubble ${sender}`;

    const isAI = sender === "ai";
    const avatar = isAI ? "🤖" : "🗣️";
    const senderName = isAI ? "Luga Assist" : "Bạn";

    const escaped = text
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/\n/g, "<br>");

    bubble.innerHTML = `
      <div class="chat-avatar" aria-hidden="true">${avatar}</div>
      <div class="chat-content">
        <div class="chat-sender">${senderName}</div>
        <div class="chat-text">${escaped}</div>
      </div>
    `;

    chatThread.appendChild(bubble);
    chatThread.scrollTop = chatThread.scrollHeight;
  }

  function appendAssistantBubble(msg) {
    const bubble = document.createElement("div");
    bubble.className = "chat-bubble ai";

    const speech = msg.speech || "Đã hoàn thành thao tác.";
    const escapedSpeech = speech
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/\n/g, "<br>");

    let actionBadgeHtml = "";
    if (msg.action_result?.details) {
      actionBadgeHtml = `<div class="chat-action-badge">⚡ ${msg.action_result.details}</div>`;
    }

    let thumbHtml = "";
    if (msg.annotated_image) {
      thumbHtml = `<img src="${msg.annotated_image}" class="chat-thumb" alt="Ảnh chụp màn hình thao tác" onclick="window.previewLargeImage('${msg.annotated_image}')" title="Nhấp để xem ảnh lớn">`;
    }

    let speakAgainBtn = `
      <button class="btn-speak-again" onclick="window.speakAgain('${encodeURIComponent(speech)}')">
        🔊 Nghe lại
      </button>
    `;

    bubble.innerHTML = `
      <div class="chat-avatar" aria-hidden="true">🤖</div>
      <div class="chat-content">
        <div class="chat-sender">Luga Assist ${msg.done ? "✅" : "⏳"}</div>
        <div class="chat-text">${escapedSpeech}</div>
        ${actionBadgeHtml}
        ${thumbHtml}
        ${speakAgainBtn}
      </div>
    `;

    chatThread.appendChild(bubble);
    chatThread.scrollTop = chatThread.scrollHeight;
  }

  window.previewLargeImage = function (imgSrc) {
    lastActionImg.src = imgSrc;
    lastActionImg.style.display = "block";
    previewPlaceholder.style.display = "none";
  };

  window.speakAgain = function (encodedText) {
    const text = decodeURIComponent(encodedText);
    fetch("/api/command", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ command: `Đọc lại: ${text}`, speak: true }),
    }).catch(console.error);
  };

  function appendLog(userCmd, aiReply, actionResult) {
    const item = document.createElement("div");
    const isSuccess = actionResult?.success !== false;
    item.className = `log-item ${isSuccess ? "success" : "error"}`;

    item.innerHTML = `
      <div class="log-user">🗣️ "${userCmd}"</div>
      <div class="log-reply">🤖 ${aiReply}</div>
      <div class="log-action">⚡ ${actionResult?.details || actionResult?.action || "Hoàn thành"}</div>
    `;

    activityLog.insertBefore(item, activityLog.firstChild);
  }

  // 4. Form Submit & Quick Chips
  chatForm.addEventListener("submit", (e) => {
    e.preventDefault();
    const val = chatInput.value.trim();
    if (val) sendCommand(val);
  });

  btnChatClear.addEventListener("click", () => {
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: "CLEAR_CHAT" }));
    }
  });

  document.querySelectorAll(".quick-chip").forEach((btn) => {
    btn.addEventListener("click", () => {
      const cmd = btn.getAttribute("data-cmd");
      if (cmd) sendCommand(cmd);
    });
  });

  btnReadScreen.addEventListener("click", () => {
    sendCommand("Hãy miêu tả chi tiết những gì đang hiển thị trên màn hình máy tính của tôi.");
  });

  // 5. Accessible Hotkeys
  window.addEventListener("keydown", (e) => {
    if (e.code === "Escape") {
      e.preventDefault();
      if (isListening) stopListening();
      if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: "STOP_SPEECH" }));
      }
      return;
    }

    if (e.code === "F4") {
      e.preventDefault();
      sendCommand("Hãy miêu tả chi tiết những gì đang hiển thị trên màn hình máy tính của tôi.");
      return;
    }

    // Space to talk (only when not focused on input)
    if (e.target.tagName !== "INPUT" && e.target.tagName !== "TEXTAREA" && e.target.tagName !== "SELECT") {
      if (e.code === "Space" && !e.repeat) {
        e.preventDefault();
        if (!isListening) startListening();
      }
    }
  });

  window.addEventListener("keyup", (e) => {
    if (e.target.tagName === "INPUT" || e.target.tagName === "TEXTAREA") return;
    if (e.code === "Space" && isListening) {
      e.preventDefault();
      setTimeout(() => {
        if (recognition && isListening) recognition.stop();
      }, 500);
    }
  });

  // 6. System Status, Mode Switcher, and Shutdown Controls
  function updateModeUI(mode) {
    currentOperatingMode = mode === "chat" ? "chat" : "control";
    if (currentOperatingMode === "chat") {
      if (modeIcon) modeIcon.innerText = "💬";
      if (modeLabel) modeLabel.innerText = "Trò chuyện AI";
      if (btnToggleMode) btnToggleMode.title = "Chế độ hiện tại: Trò chuyện AI. Bấm để đổi sang Điều khiển PC.";
      if (modalCurrentMode) modalCurrentMode.innerText = "💬 Trò chuyện AI";
      if (btnModalSwitchMode) btnModalSwitchMode.innerText = "🔄 Đổi sang Điều khiển PC";
    } else {
      if (modeIcon) modeIcon.innerText = "🎮";
      if (modeLabel) modeLabel.innerText = "Điều khiển PC";
      if (btnToggleMode) btnToggleMode.title = "Chế độ hiện tại: Điều khiển máy tính. Bấm để đổi sang Trò chuyện AI.";
      if (modalCurrentMode) modalCurrentMode.innerText = "🎮 Điều khiển máy tính";
      if (btnModalSwitchMode) btnModalSwitchMode.innerText = "🔄 Đổi sang Trò chuyện AI";
    }
  }

  async function toggleOperatingMode() {
    const targetMode = currentOperatingMode === "control" ? "chat" : "control";
    try {
      const res = await fetch("/api/set_mode", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ mode: targetMode, announce: true })
      });
      const data = await res.json();
      if (data.mode) {
        updateModeUI(data.mode);
      }
    } catch (e) {
      console.error("Failed to toggle mode:", e);
    }
  }

  async function fetchSystemStatus() {
    try {
      const res = await fetch("/api/system/status");
      const data = await res.json();
      if (modalServerStatus) modalServerStatus.innerText = "🟢 Đang chạy (Port 8000)";
      if (modalScreenRes) modalScreenRes.innerText = `🖥️ ${data.screen_resolution || "1920x1080"}`;
      if (modalPid) modalPid.innerText = `PID: ${data.pid || "-"}`;
      if (data.gemini_ready) {
        if (modalGeminiStatus) modalGeminiStatus.innerText = "🟢 Đã sẵn sàng";
      } else {
        if (modalGeminiStatus) modalGeminiStatus.innerText = "🟡 Đang chờ kết nối";
      }
      if (data.mode) {
        updateModeUI(data.mode);
      }
    } catch (e) {
      if (modalServerStatus) modalServerStatus.innerText = "🔴 Không phản hồi";
    }
  }

  const selectMicDevice = document.getElementById("selectMicDevice");
  const btnTestMicLevel = document.getElementById("btnTestMicLevel");
  const micTestStatus = document.getElementById("micTestStatus");

  async function fetchAudioDevices() {
    if (!selectMicDevice) return;
    try {
      const res = await fetch("/api/audio/devices");
      const data = await res.json();
      if (data.status === "ok" && Array.isArray(data.devices)) {
        selectMicDevice.innerHTML = "";
        data.devices.forEach((dev) => {
          const opt = document.createElement("option");
          opt.value = dev.name;
          opt.textContent = `${dev.name}${dev.is_default ? " (Mặc định)" : ""}`;
          if (dev.name === data.active_name || dev.id === data.active_id) {
            opt.selected = true;
          }
          selectMicDevice.appendChild(opt);
        });
      }
    } catch (e) {
      console.error("Failed to fetch audio devices:", e);
    }
  }

  if (selectMicDevice) {
    selectMicDevice.addEventListener("change", async () => {
      const chosenName = selectMicDevice.value;
      if (!chosenName) return;
      if (micTestStatus) {
        micTestStatus.textContent = "⏳ Đang chuyển đổi Microphone...";
        micTestStatus.style.color = "#38bdf8";
      }
      try {
        const res = await fetch("/api/audio/device", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ device: chosenName })
        });
        const data = await res.json();
        if (micTestStatus) {
          micTestStatus.textContent = `✅ Đã chọn: ${data.active_name || chosenName}`;
          micTestStatus.style.color = "#4ade80";
        }
      } catch (e) {
        if (micTestStatus) {
          micTestStatus.textContent = "❌ Lỗi khi đổi micro";
          micTestStatus.style.color = "#f87171";
        }
      }
    });
  }

  if (btnTestMicLevel) {
    btnTestMicLevel.addEventListener("click", async () => {
      if (micTestStatus) {
        micTestStatus.textContent = "⏳ Đang thử micro (vui lòng nói gì đó vào mic)...";
        micTestStatus.style.color = "#fbbf24";
      }
      try {
        const res = await fetch("/api/audio/test", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ duration: 0.8 })
        });
        const data = await res.json();
        if (micTestStatus) {
          if (data.has_signal) {
            micTestStatus.textContent = `✅ Tín hiệu tốt! RMS: ${data.avg_rms} (Peak: ${data.peak_rms})`;
            micTestStatus.style.color = "#4ade80";
            soundSuccess();
          } else {
            micTestStatus.textContent = `⚠️ Tín hiệu quá nhỏ hoặc im lặng (RMS: ${data.avg_rms}). Hãy chọn Micro khác!`;
            micTestStatus.style.color = "#f87171";
            soundError();
          }
        }
      } catch (e) {
        if (micTestStatus) {
          micTestStatus.textContent = "❌ Không thể kiểm tra tín hiệu micro.";
          micTestStatus.style.color = "#f87171";
        }
      }
    });
  }

  function openStatusModal() {
    fetchSystemStatus();
    fetchAudioDevices();
    if (statusModal) statusModal.style.display = "flex";
  }

  function closeStatusModal() {
    if (statusModal) statusModal.style.display = "none";
  }

  function openShutdownModal() {
    closeStatusModal();
    if (shutdownModal) shutdownModal.style.display = "flex";
  }

  function closeShutdownModal() {
    if (shutdownModal) shutdownModal.style.display = "none";
  }

  async function performShutdown() {
    closeShutdownModal();
    soundStopListening();
    appendChatBubble("ai", "🛑 Đang tắt Luga Assist. Tạm biệt bạn! Cửa sổ này có thể đóng lại.");
    try {
      await fetch("/api/system/shutdown", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ speak: true, delay: 1.0 })
      });
    } catch (e) {
      console.log("Shutdown requested.");
    }
  }

  async function performRestart() {
    closeStatusModal();
    appendChatBubble("ai", "🔄 Luga Assist đang khởi động lại...");
    try {
      await fetch("/api/system/restart", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ delay: 1.0 })
      });
      setTimeout(() => window.location.reload(), 3000);
    } catch (e) {
      console.log("Restart requested.");
    }
  }

  // Modal & Action Listeners
  if (btnSystemStatus) btnSystemStatus.addEventListener("click", openStatusModal);
  if (btnCloseStatusModal) btnCloseStatusModal.addEventListener("click", closeStatusModal);
  if (btnToggleMode) btnToggleMode.addEventListener("click", toggleOperatingMode);
  if (btnModalSwitchMode) btnModalSwitchMode.addEventListener("click", toggleOperatingMode);
  if (btnHeaderShutdown) btnHeaderShutdown.addEventListener("click", openShutdownModal);
  if (btnCloseShutdownModal) btnCloseShutdownModal.addEventListener("click", closeShutdownModal);
  if (btnCancelShutdown) btnCancelShutdown.addEventListener("click", closeShutdownModal);
  if (btnConfirmShutdown) btnConfirmShutdown.addEventListener("click", performShutdown);
  if (btnModalShutdown) btnModalShutdown.addEventListener("click", openShutdownModal);
  if (btnModalRestart) btnModalRestart.addEventListener("click", performRestart);

  if (btnTestVoice) {
    btnTestVoice.addEventListener("click", () => {
      sendCommand("Xin chào, tôi là Luga Assist. Giọng nói và hệ thống đang hoạt động rất tốt!");
      closeStatusModal();
    });
  }

  const btnOpenPopup = document.getElementById("btnOpenPopup");
  if (btnOpenPopup) {
    btnOpenPopup.addEventListener("click", () => {
      window.open('/popup', 'LugaMiniPopup', 'width=460,height=600,top=100,left=100,resizable=yes');
    });
  }

  // Close modals when clicking backdrop
  window.addEventListener("click", (e) => {
    if (e.target === statusModal) closeStatusModal();
    if (e.target === shutdownModal) closeShutdownModal();
  });

  // Initialize
  fetchSystemStatus();
  connectWebSocket();
});
