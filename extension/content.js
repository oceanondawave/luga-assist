/**
 * Luga Assist - Content Script for https://gemini.google.com
 * Handles automated session interaction, screenshot pasting, prompt submission,
 * response monitoring, and new chat reset when overloaded.
 */

(function () {
  console.log("[Luga Assist] Content script loaded on gemini.google.com");

  let ws = null;
  let isConnected = false;
  let chatTurnsCount = 0;
  const MAX_TURNS = 15;
  let isProcessingTask = false;

  // 1. Create Floating UI Widget
  const widget = document.createElement("div");
  widget.id = "luga-assist-widget";
  widget.innerHTML = `
    <div style="
      position: fixed;
      bottom: 24px;
      right: 24px;
      z-index: 999999;
      background: #111827;
      color: #F9FAFB;
      border: 2px solid #3B82F6;
      border-radius: 12px;
      padding: 12px 16px;
      box-shadow: 0 10px 25px rgba(0,0,0,0.5);
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
      font-size: 13px;
      display: flex;
      flex-direction: column;
      gap: 8px;
      min-width: 230px;
    ">
      <div style="display: flex; align-items: center; justify-content: space-between;">
        <span style="font-weight: 700; color: #60A5FA;">LUGA ASSIST BRIDGE</span>
        <span id="luga-status-dot" style="
          width: 10px;
          height: 10px;
          border-radius: 50%;
          background: #EF4444;
          display: inline-block;
        "></span>
      </div>
      <div id="luga-status-text" style="color: #9CA3AF;">Đang kết nối tới Local Agent...</div>
      <div style="display: flex; justify-content: space-between; align-items: center; font-size: 11px; color: #D1D5DB;">
        <span>Phiên: <b id="luga-turns-count">0</b>/${MAX_TURNS} lượt</span>
        <button id="luga-btn-new-chat" style="
          background: #2563EB;
          color: white;
          border: none;
          border-radius: 6px;
          padding: 4px 8px;
          cursor: pointer;
          font-weight: 600;
        ">Tạo Chat Mới</button>
      </div>
    </div>
  `;
  document.body.appendChild(widget);

  const statusDot = document.getElementById("luga-status-dot");
  const statusText = document.getElementById("luga-status-text");
  const turnsCountElem = document.getElementById("luga-turns-count");
  const btnNewChat = document.getElementById("luga-btn-new-chat");

  btnNewChat.addEventListener("click", () => {
    triggerNewChat();
  });

  function updateStatus(connected, message) {
    isConnected = connected;
    if (connected) {
      statusDot.style.background = "#10B981";
      statusDot.style.boxShadow = "0 0 8px #10B981";
      statusText.innerText = message || "Đã kết nối Local Agent (Sẵn sàng)";
    } else {
      statusDot.style.background = "#EF4444";
      statusDot.style.boxShadow = "none";
      statusText.innerText = message || "Mất kết nối. Đang thử lại...";
    }
    turnsCountElem.innerText = chatTurnsCount;

    try {
      chrome.runtime.sendMessage({ type: "STATUS_UPDATE", connected: connected });
    } catch (e) {}
  }

  // 2. Connect WebSocket to Local Agent
  function connectWebSocket() {
    const WS_URL = "ws://127.0.0.1:8000/ws/extension";
    try {
      ws = new WebSocket(WS_URL);

      ws.onopen = () => {
        console.log("[Luga Assist] WebSocket connected to Local Agent.");
        updateStatus(true);
      };

      ws.onclose = () => {
        updateStatus(false, "Mất kết nối tới Local Agent (Cổng 8000)");
        setTimeout(connectWebSocket, 2500);
      };

      ws.onerror = (err) => {
        console.warn("[Luga Assist] WebSocket error:", err);
      };

      ws.onmessage = async (event) => {
        try {
          const data = JSON.parse(event.data);
          if (data.type === "EXECUTE_COMMAND") {
            handleExecuteCommand(data);
          } else if (data.type === "RESET_CHAT") {
            triggerNewChat();
          }
        } catch (e) {
          console.error("[Luga Assist] Failed to parse message:", e);
        }
      };
    } catch (err) {
      updateStatus(false, "Không thể kết nối. Đang thử lại...");
      setTimeout(connectWebSocket, 3000);
    }
  }

  // 3. Helper: Trigger New Chat
  async function triggerNewChat() {
    console.log("[Luga Assist] Triggering New Chat...");
    chatTurnsCount = 0;
    turnsCountElem.innerText = "0";

    // Selectors for New Chat in Gemini
    const selectors = [
      "a[href='/app']",
      "button[aria-label*='New chat' i]",
      "button[aria-label*='Cuộc trò chuyện mới' i]",
      "[data-test-id='new-chat-button']",
      ".new-chat-button"
    ];

    for (const sel of selectors) {
      const btn = document.querySelector(sel);
      if (btn) {
        btn.click();
        console.log("[Luga Assist] Clicked New Chat button via:", sel);
        await sleep(1500);
        return true;
      }
    }

    // Fallback: Navigate to /app
    if (window.location.pathname !== "/app") {
      window.location.href = "https://gemini.google.com/app";
      await sleep(2000);
    }
    return true;
  }

  // 4. Helper: Sleep
  function sleep(ms) {
    return new Promise((resolve) => setTimeout(resolve, ms));
  }

  // 5. Helper: Convert Base64 Data URI to File object
  async function dataURItoFile(dataURI, filename = "screenshot.jpg") {
    const res = await fetch(dataURI);
    const blob = await res.blob();
    return new File([blob], filename, { type: blob.type || "image/jpeg" });
  }

  // 6. Helper: Find Composer Elements
  function getComposerElements() {
    const editor =
      document.querySelector("rich-textarea .ql-editor") ||
      document.querySelector("rich-textarea div[contenteditable='true']") ||
      document.querySelector("div[contenteditable='true'][role='textbox']") ||
      document.querySelector("rich-textarea") ||
      document.querySelector("textarea");

    const sendBtn =
      document.querySelector("button[aria-label*='Send message' i]") ||
      document.querySelector("button[aria-label*='Gửi tin nhắn' i]") ||
      document.querySelector("button[aria-label*='Send' i]") ||
      document.querySelector("button[aria-label*='Gửi' i]") ||
      document.querySelector("button.send-button") ||
      document.querySelector("button.send-button-container");

    const fileInput = document.querySelector("input[type='file']");

    return { editor, sendBtn, fileInput };
  }

  // 7. Inject Image (Screenshot) into Gemini Web
  async function injectScreenshot(imageBase64) {
    if (!imageBase64) return false;

    console.log("[Luga Assist] Attaching screenshot to Gemini...");
    const file = await dataURItoFile(imageBase64, "screen.jpg");
    const { editor, fileInput } = getComposerElements();

    if (!editor) {
      console.error("[Luga Assist] Editor element not found!");
      return false;
    }

    editor.focus();

    // Strategy A: Paste Event via ClipboardEvent
    try {
      const dt = new DataTransfer();
      dt.items.add(file);

      const pasteEvent = new ClipboardEvent("paste", {
        bubbles: true,
        cancelable: true,
        clipboardData: dt,
      });

      editor.dispatchEvent(pasteEvent);
      console.log("[Luga Assist] Dispatched paste event with screenshot.");
      await sleep(1500);

      // Verify if image thumbnail appeared
      const hasImagePreview = document.querySelector("img[src^='blob:'], .image-preview, [data-test-id='image-preview']");
      if (hasImagePreview) return true;
    } catch (e) {
      console.warn("[Luga Assist] Paste event attempt error:", e);
    }

    // Strategy B: Hidden File Input Drop/Change
    if (fileInput) {
      try {
        const dt = new DataTransfer();
        dt.items.add(file);
        fileInput.files = dt.files;
        fileInput.dispatchEvent(new Event("change", { bubbles: true }));
        console.log("[Luga Assist] Injected screenshot via file input.");
        await sleep(1500);
        return true;
      } catch (e) {
        console.warn("[Luga Assist] File input attempt error:", e);
      }
    }

    // Strategy C: Drag & Drop on Editor
    try {
      const dt = new DataTransfer();
      dt.items.add(file);
      editor.dispatchEvent(new DragEvent("dragenter", { bubbles: true, dataTransfer: dt }));
      editor.dispatchEvent(new DragEvent("dragover", { bubbles: true, dataTransfer: dt }));
      editor.dispatchEvent(new DragEvent("drop", { bubbles: true, dataTransfer: dt }));
      console.log("[Luga Assist] Injected screenshot via Drop event.");
      await sleep(1500);
      return true;
    } catch (e) {
      console.warn("[Luga Assist] Drag-drop attempt error:", e);
    }

    return true;
  }

  // 8. Inject Text Prompt into Editor
  async function injectPrompt(promptText) {
    const { editor } = getComposerElements();
    if (!editor) return false;

    editor.focus();

    // Clear any previous placeholder
    const pTag = editor.querySelector("p") || editor;
    pTag.focus();

    // Try document.execCommand first for natural input simulation
    const success = document.execCommand("insertText", false, promptText);
    if (!success) {
      pTag.innerText = promptText;
      editor.dispatchEvent(new Event("input", { bubbles: true }));
      editor.dispatchEvent(new Event("change", { bubbles: true }));
    }

    await sleep(800);
    return true;
  }

  // 9. Wait for Gemini Generation to Complete
  function waitForGeminiResponse() {
    return new Promise((resolve, reject) => {
      let timeoutTimer = null;
      let lastText = "";
      let stableCount = 0;

      // Timeout safety: 40 seconds max
      timeoutTimer = setTimeout(() => {
        clearInterval(checkInterval);
        resolve(getLatestResponseText());
      }, 40000);

      const checkInterval = setInterval(() => {
        // Check if "Stop" button is present
        const stopBtn =
          document.querySelector("button[aria-label*='Stop' i]") ||
          document.querySelector("button[aria-label*='Dừng' i]");

        const currentText = getLatestResponseText();

        if (stopBtn) {
          // Still streaming
          stableCount = 0;
          return;
        }

        // When Stop button is gone or not found, verify text stability
        if (currentText && currentText === lastText && currentText.length > 20) {
          stableCount++;
          if (stableCount >= 2) {
            // Text is stable for ~1.5s
            clearInterval(checkInterval);
            clearTimeout(timeoutTimer);
            resolve(currentText);
          }
        } else {
          lastText = currentText;
          stableCount = 0;
        }
      }, 700);
    });
  }

  function getLatestResponseText() {
    const responseContainers = document.querySelectorAll(
      "message-content, .model-response-text, .response-container, [data-test-id='model-response']"
    );
    if (responseContainers.length > 0) {
      const latest = responseContainers[responseContainers.length - 1];
      return latest.innerText || latest.textContent || "";
    }
    return "";
  }

  // 10. Main Execution Handler
  async function handleExecuteCommand(task) {
    if (isProcessingTask) {
      console.warn("[Luga Assist] Already processing another task, queuing...");
    }
    isProcessingTask = true;
    statusText.innerText = "Đang gửi lệnh tới Gemini...";

    try {
      // Check session overload
      chatTurnsCount++;
      turnsCountElem.innerText = chatTurnsCount;
      if (chatTurnsCount >= MAX_TURNS) {
        console.log("[Luga Assist] Max turns reached, creating new chat...");
        await triggerNewChat();
      }

      // Step 1: Inject Screenshot
      if (task.imageBase64) {
        await injectScreenshot(task.imageBase64);
      }

      // Step 2: Inject Prompt
      await injectPrompt(task.prompt);

      // Step 3: Click Send Button
      await sleep(1000);
      const { sendBtn, editor } = getComposerElements();
      if (sendBtn && !sendBtn.disabled) {
        sendBtn.click();
        console.log("[Luga Assist] Clicked Send button.");
      } else {
        // Fallback: send Enter keydown
        editor.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", keyCode: 13, bubbles: true }));
        console.log("[Luga Assist] Sent Enter keydown event.");
      }

      statusText.innerText = "Gemini đang suy nghĩ...";

      // Step 4: Wait for Generation
      await sleep(1500); // Wait for generation to start
      const rawResponse = await waitForGeminiResponse();
      console.log("[Luga Assist] Gemini Response received:", rawResponse);

      statusText.innerText = "Đã nhận kết quả, đang thực hiện...";

      // Step 5: Send result back to Local Agent
      ws.send(
        JSON.stringify({
          type: "COMMAND_RESULT",
          id: task.id,
          raw_text: rawResponse,
          success: true,
        })
      );
    } catch (err) {
      console.error("[Luga Assist] Error during command execution:", err);
      ws.send(
        JSON.stringify({
          type: "COMMAND_RESULT",
          id: task.id,
          raw_text: "",
          success: false,
          error: String(err),
        })
      );
      updateStatus(true, "Lỗi thực thi lệnh");
    } finally {
      isProcessingTask = false;
      setTimeout(() => {
        if (isConnected) updateStatus(true, "Sẵn sàng nhận lệnh mới");
      }, 2000);
    }
  }

  // Start connection
  connectWebSocket();
})();
