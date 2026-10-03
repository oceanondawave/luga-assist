/**
 * Luga Assist - Content Script for https://gemini.google.com
 * Handles automated session interaction, screenshot pasting, prompt submission,
 * and response monitoring.
 * Preserves the continuous chat thread so Gemini understands full conversation context.
 */

(function () {
  console.log("[Luga Assist] Content script running silently on gemini.google.com");

  let ws = null;
  let isConnected = false;
  let isProcessingTask = false;

  // 1. Connect WebSocket to Local Agent
  function connectWebSocket() {
    const WS_URL = "ws://127.0.0.1:8000/ws/extension";
    try {
      ws = new WebSocket(WS_URL);

      ws.onopen = () => {
        isConnected = true;
        console.log("[Luga Assist] Content script connected to Local Agent.");
      };

      ws.onclose = () => {
        isConnected = false;
        setTimeout(connectWebSocket, 4000);
      };

      ws.onerror = () => {
        // Silent error
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
      setTimeout(connectWebSocket, 4000);
    }
  }

  // 2. Trigger New Chat ONLY when explicitly requested
  async function triggerNewChat() {
    console.log("[Luga Assist] Người dùng yêu cầu tạo cuộc trò chuyện mới...");

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
        await sleep(1500);
        return true;
      }
    }

    if (window.location.pathname !== "/app") {
      window.location.href = "https://gemini.google.com/app";
      await sleep(2000);
    }
    return true;
  }

  // 3. Helper: Sleep
  function sleep(ms) {
    return new Promise((resolve) => setTimeout(resolve, ms));
  }

  // 4. Helper: Convert Base64 Data URI to File object
  async function dataURItoFile(dataURI, filename = "screenshot.jpg") {
    const res = await fetch(dataURI);
    const blob = await res.blob();
    return new File([blob], filename, { type: blob.type || "image/jpeg" });
  }

  // 5. Helper: Find Composer Elements
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

  // 6. Inject Image (Screenshot) into Gemini Web
  async function injectScreenshot(imageBase64) {
    if (!imageBase64) return false;

    console.log("[Luga Assist] Đang đính kèm ảnh chụp màn hình vào phiên chat hiện tại...");
    const file = await dataURItoFile(imageBase64, "screen.jpg");
    const { editor, fileInput } = getComposerElements();

    if (!editor) return false;

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
      await sleep(1500);

      const hasImagePreview = document.querySelector("img[src^='blob:'], .image-preview, [data-test-id='image-preview']");
      if (hasImagePreview) return true;
    } catch (e) {}

    // Strategy B: Hidden File Input Drop/Change
    if (fileInput) {
      try {
        const dt = new DataTransfer();
        dt.items.add(file);
        fileInput.files = dt.files;
        fileInput.dispatchEvent(new Event("change", { bubbles: true }));
        await sleep(1500);
        return true;
      } catch (e) {}
    }

    // Strategy C: Drag & Drop on Editor
    try {
      const dt = new DataTransfer();
      dt.items.add(file);
      editor.dispatchEvent(new DragEvent("dragenter", { bubbles: true, dataTransfer: dt }));
      editor.dispatchEvent(new DragEvent("dragover", { bubbles: true, dataTransfer: dt }));
      editor.dispatchEvent(new DragEvent("drop", { bubbles: true, dataTransfer: dt }));
      await sleep(1500);
      return true;
    } catch (e) {}

    return true;
  }

  // 7. Inject Text Prompt into Editor
  async function injectPrompt(promptText) {
    const { editor } = getComposerElements();
    if (!editor) return false;

    editor.focus();

    const pTag = editor.querySelector("p") || editor;
    pTag.focus();

    const success = document.execCommand("insertText", false, promptText);
    if (!success) {
      pTag.innerText = promptText;
      editor.dispatchEvent(new Event("input", { bubbles: true }));
      editor.dispatchEvent(new Event("change", { bubbles: true }));
    }

    await sleep(800);
    return true;
  }

  // 8. Wait for Gemini Generation to Complete
  function waitForGeminiResponse() {
    return new Promise((resolve) => {
      let timeoutTimer = null;
      let lastText = "";
      let stableCount = 0;

      timeoutTimer = setTimeout(() => {
        clearInterval(checkInterval);
        resolve(getLatestResponseText());
      }, 40000);

      const checkInterval = setInterval(() => {
        const stopBtn =
          document.querySelector("button[aria-label*='Stop' i]") ||
          document.querySelector("button[aria-label*='Dừng' i]");

        const currentText = getLatestResponseText();

        if (stopBtn) {
          stableCount = 0;
          return;
        }

        if (currentText && currentText === lastText && currentText.length > 20) {
          stableCount++;
          if (stableCount >= 2) {
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

  // 9. Main Execution Handler (ALWAYS KEEPS CONTINUOUS CHAT THREAD)
  async function handleExecuteCommand(task) {
    if (isProcessingTask) {
      console.warn("[Luga Assist] Đang xử lý câu lệnh trước, xếp hàng tiếp theo...");
    }
    isProcessingTask = true;

    try {
      // NOTE: We DO NOT trigger new chat here!
      // All requests are added to the SAME continuous conversation thread
      // so Gemini maintains full context and history!

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
      } else {
        editor.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", keyCode: 13, bubbles: true }));
      }

      // Step 4: Wait for Generation in the current thread
      await sleep(1500);
      const rawResponse = await waitForGeminiResponse();

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
      console.error("[Luga Assist] Lỗi khi thực thi lệnh:", err);
      ws.send(
        JSON.stringify({
          type: "COMMAND_RESULT",
          id: task.id,
          raw_text: "",
          success: false,
          error: String(err),
        })
      );
    } finally {
      isProcessingTask = false;
    }
  }

  // Start connection
  connectWebSocket();
})();
