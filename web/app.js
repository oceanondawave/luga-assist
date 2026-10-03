/**
 * Luga Assist - Web Interface Logic
 * Handles Web Speech API (Vietnamese), WebSockets, Sound Earcons, and Accessible Hotkeys.
 */

document.addEventListener("DOMContentLoaded", () => {
  // DOM Elements
  const btnMic = document.getElementById("btnMic");
  const speechDisplay = document.getElementById("speechDisplay");
  const agentDot = document.getElementById("agentDot");
  const agentStatusText = document.getElementById("agentStatusText");
  const extDot = document.getElementById("extDot");
  const extStatusText = document.getElementById("extStatusText");
  const activityLog = document.getElementById("activityLog");
  const previewPlaceholder = document.getElementById("previewPlaceholder");
  const lastActionImg = document.getElementById("lastActionImg");
  const selectVoice = document.getElementById("selectVoice");
  const btnReadScreen = document.getElementById("btnReadScreen");

  let ws = null;
  let isListening = false;
  let recognition = null;
  let audioCtx = null;
  let continuousMode = false;

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

  // 1. Initialize Web Speech API for Vietnamese
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;

  if (SpeechRecognition) {
    recognition = new SpeechRecognition();
    recognition.lang = "vi-VN"; // Vietnamese language
    recognition.continuous = false;
    recognition.interimResults = true;
    recognition.maxAlternatives = 1;

    recognition.onstart = () => {
      isListening = true;
      btnMic.classList.add("listening");
      speechDisplay.innerText = "Đang lắng nghe giọng nói của bạn...";
      speechDisplay.style.borderColor = "var(--accent-red)";
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
        speechDisplay.innerText = interimTranscript;
      }

      if (finalTranscript) {
        finalTranscript = finalTranscript.trim();
        speechDisplay.innerText = `"${finalTranscript}"`;
        sendVoiceCommand(finalTranscript);
      }
    };

    recognition.onerror = (event) => {
      console.warn("[SpeechRecognition] Error:", event.error);
      if (event.error !== "no-speech") {
        speechDisplay.innerText = `Lỗi nhận diện âm thanh: ${event.error}`;
        soundError();
      }
      stopListening();
    };

    recognition.onend = () => {
      stopListening();
      if (continuousMode) {
        setTimeout(startListening, 1000);
      }
    };
  } else {
    speechDisplay.innerText = "Trình duyệt của bạn không hỗ trợ Web Speech API. Vui lòng mở bằng Google Chrome.";
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
    speechDisplay.style.borderColor = "var(--border)";
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

  // 2. Connect WebSocket to Local Agent
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
      // Update Gemini connection status
      if (msg.gemini_ready || msg.extension_connected) {
        extDot.classList.add("online");
        extStatusText.innerText = "Google Gemini: Đã sẵn sàng (Chạy ngầm)";
      } else {
        extDot.classList.remove("online");
        extStatusText.innerText = "Google Gemini: Đang chờ Extension";
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
    } else if (msg.type === "ERROR") {
      speechDisplay.innerText = `Lỗi: ${msg.message}`;
      soundError();
      appendLog(msg.user_command || "Thao tác", msg.message, { success: false });
    }
  }

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

  // 3. Hotkey Accessibility Handlers
  window.addEventListener("keydown", (e) => {
    // Avoid triggering when focused on select or inputs
    if (e.target.tagName === "INPUT" || e.target.tagName === "SELECT") return;

    if (e.code === "Space" && !e.repeat) {
      e.preventDefault();
      if (!isListening) startListening();
    } else if (e.code === "Escape") {
      e.preventDefault();
      if (isListening) stopListening();
      if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: "STOP_SPEECH" }));
      }
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
      e.preventDefault();
      setTimeout(() => {
        if (recognition && isListening) recognition.stop();
      }, 500);
    }
  });

  // Read screen button
  function triggerReadScreen() {
    sendVoiceCommand("Hãy miêu tả chi tiết những gì đang hiển thị trên màn hình máy tính của tôi.");
  }

  btnReadScreen.addEventListener("click", triggerReadScreen);

  // Initialize
  connectWebSocket();
});
