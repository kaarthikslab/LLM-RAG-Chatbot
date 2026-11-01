const pdfInput = document.getElementById("pdf-input");
const uploadZone = document.getElementById("upload-zone");
const uploadMessage = document.getElementById("upload-message");
const welcomeView = document.getElementById("welcome-view");
const chatView = document.getElementById("chat-view");
const messages = document.getElementById("messages");
const chatForm = document.getElementById("chat-form");
const questionInput = document.getElementById("question-input");
const sendBtn = document.getElementById("send-btn");
const newSessionBtn = document.getElementById("new-session-btn");
const documentName = document.getElementById("document-name");
const documentStatus = document.getElementById("document-status");
const sessionLabel = document.getElementById("session-label");
const topTitle = document.getElementById("top-title");

let currentSessionId = null;
let busy = false;

function setBusy(value) {
  busy = value;
  sendBtn.disabled = value;
  questionInput.disabled = value;
  sendBtn.textContent = value ? "…" : "↑";
}

function setSessionActive(active) {
  document.querySelector(".status-dot").classList.toggle("active", active);
  sessionLabel.textContent = active ? "Session active" : "No active session";
  newSessionBtn.disabled = !active;
}

function showChat() {
  welcomeView.classList.add("hidden");
  chatView.classList.remove("hidden");
  topTitle.textContent = "Ask your document";
}

function showWelcome() {
  chatView.classList.add("hidden");
  welcomeView.classList.remove("hidden");
  topTitle.textContent = "Chat with your PDF";
  messages.innerHTML = "";
}

function addMessage(role, text, sources = []) {
  const wrapper = document.createElement("article");
  wrapper.className = `message ${role}`;

  const avatar = document.createElement("div");
  avatar.className = "avatar";
  avatar.textContent = role === "user" ? "You" : "AI";

  const body = document.createElement("div");
  body.className = "message-body";

  const name = document.createElement("div");
  name.className = "message-name";
  name.textContent = role === "user" ? "You" : "PaperPilot";

  const content = document.createElement("div");
  content.className = "message-text";
  content.textContent = text;

  body.append(name, content);

  if (role === "assistant" && sources.length) {
    const details = document.createElement("details");
    details.className = "sources";
    const summary = document.createElement("summary");
    summary.textContent = `Sources (${sources.length} retrieved chunks)`;
    details.appendChild(summary);

    sources.forEach((source) => {
      const item = document.createElement("div");
      item.className = "source-item";
      const heading = document.createElement("strong");
      heading.textContent = `Page ${source.page} · Source ${source.source}`;
      const preview = document.createElement("div");
      preview.textContent = source.preview;
      item.append(heading, preview);
      details.appendChild(item);
    });
    body.appendChild(details);
  }

  wrapper.append(avatar, body);
  messages.appendChild(wrapper);
  messages.scrollTop = messages.scrollHeight;
  return wrapper;
}

async function uploadPdf(file) {
  if (!file) return;
  if (!file.name.toLowerCase().endsWith(".pdf")) {
    uploadMessage.textContent = "Please choose a PDF file.";
    return;
  }

  uploadMessage.textContent = "Uploading and processing your PDF…";
  uploadZone.style.pointerEvents = "none";

  try {
    const formData = new FormData();
    formData.append("file", file);

    const response = await fetch("/api/sessions/upload", {
      method: "POST",
      body: formData,
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || "PDF upload failed.");

    currentSessionId = data.session_id;
    documentName.textContent = data.filename;
    documentStatus.textContent = `${data.pages} pages · ${data.chunks} text chunks`;
    setSessionActive(true);
    uploadMessage.textContent = "";
    showChat();
    addMessage(
      "assistant",
      `I've processed "${data.filename}". You can now ask questions about this PDF. Follow-up questions are supported, so you can refer to earlier topics naturally.`
    );
  } catch (error) {
    uploadMessage.textContent = error.message;
  } finally {
    uploadZone.style.pointerEvents = "";
    pdfInput.value = "";
  }
}

pdfInput.addEventListener("change", (event) => uploadPdf(event.target.files[0]));

async function startNewSession() {
  if (!currentSessionId || busy) return;
  const oldSessionId = currentSessionId;
  currentSessionId = null;

  try {
    await fetch(`/api/sessions/${encodeURIComponent(oldSessionId)}`, {
      method: "DELETE",
    });
  } catch (_) {
    // The browser still resets locally; server-side sessions are in memory.
  }

  documentName.textContent = "No document uploaded";
  documentStatus.textContent = "Upload a PDF to begin";
  setSessionActive(false);
  showWelcome();
  uploadMessage.textContent = "Previous session closed. Upload a new PDF to begin.";
  pdfInput.click();
}

newSessionBtn.addEventListener("click", startNewSession);

chatForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const question = questionInput.value.trim();
  if (!question || !currentSessionId || busy) return;

  addMessage("user", question);
  questionInput.value = "";
  questionInput.style.height = "auto";
  const typing = addMessage("assistant", "Thinking…");
  typing.querySelector(".message-text").classList.add("typing");
  setBusy(true);

  try {
    const response = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        session_id: currentSessionId,
        question,
      }),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || "Something went wrong.");

    typing.remove();
    addMessage("assistant", data.answer, data.sources || []);
  } catch (error) {
    typing.remove();
    addMessage("assistant", `Sorry, I couldn't answer that: ${error.message}`);
  } finally {
    setBusy(false);
    questionInput.focus();
  }
});

questionInput.addEventListener("input", () => {
  questionInput.style.height = "auto";
  questionInput.style.height = `${Math.min(questionInput.scrollHeight, 130)}px`;
});

questionInput.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    chatForm.requestSubmit();
  }
});
