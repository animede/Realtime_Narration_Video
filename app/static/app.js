const form = document.querySelector("#form");
const videoStack = document.querySelector("#video-stack");
const players = [document.querySelector("#player-a"), document.querySelector("#player-b")];
const statusLabel = document.querySelector("#status");
const bufferLabel = document.querySelector("#buffer");
const caption = document.querySelector("#caption");
const chunkList = document.querySelector("#chunks");
const chatForm = document.querySelector("#chat-form");
const assistantLive = document.querySelector("#assistant-live");
const profileSelect = document.querySelector("#video-profile");
const characterDrop = document.querySelector("#character-drop");
const characterInput = document.querySelector("#character-input");
const characterPreview = document.querySelector("#character-preview");
const stageCharacter = document.querySelector("#stage-character");
const textDrop = document.querySelector("#text-drop");
const textFileInput = document.querySelector("#text-file");
const narrationText = document.querySelector("#narration-text");
const textFileName = document.querySelector("#text-file-name");
let sessionId = null;
let nextIndex = 0;
let playingIndex = null;
let playbackStarted = false;
let activePlayer = 0;
let preloadedIndex = null;
let latestSession = null;
let eventSource = null;
let lastEndedAt = null;
let switchGapMs = null;
const profileSizes = {
  "16fps-resolution": [640, 352], "16fps-5x3": [640, 384], "16fps-3x2": [576, 384],
  "16fps-4x3-resolution": [512, 384], "16fps-portrait-3x4": [384, 512],
  "16fps-portrait": [384, 640], "20fps-hq": [576, 320],
  "20fps-4x3-balanced": [512, 384], "24fps-fast": [512, 288],
  "24fps-3x2": [480, 320], "24fps-portrait": [288, 512]
};

function applyAspectRatio() {
  const [width, height] = profileSizes[profileSelect.value];
  videoStack.style.aspectRatio = `${width} / ${height}`;
  document.querySelector(".player-panel").classList.toggle("portrait", height > width);
}
profileSelect.addEventListener("change", applyAspectRatio);
applyAspectRatio();

function setDroppedFile(input, file) {
  const transfer = new DataTransfer();
  transfer.items.add(file);
  input.files = transfer.files;
  input.dispatchEvent(new Event("change", {bubbles: true}));
}

function installDropZone(zone, onFile) {
  ["dragenter", "dragover"].forEach(type => zone.addEventListener(type, event => {
    event.preventDefault();
    zone.classList.add("drag-over");
  }));
  ["dragleave", "drop"].forEach(type => zone.addEventListener(type, event => {
    event.preventDefault();
    zone.classList.remove("drag-over");
  }));
  zone.addEventListener("drop", event => {
    const file = event.dataTransfer.files[0];
    if (file) onFile(file);
  });
}

let previewUrl = null;
function useCharacterFile(file) {
  if (!file.type.startsWith("image/") || !/[.](png|jpe?g|webp)$/i.test(file.name)) {
    statusLabel.textContent = "PNG・JPEG・WebP画像を選択してください";
    return;
  }
  setDroppedFile(characterInput, file);
}

characterInput.addEventListener("change", () => {
  const file = characterInput.files[0];
  if (!file) return;
  if (previewUrl) URL.revokeObjectURL(previewUrl);
  previewUrl = URL.createObjectURL(file);
  characterPreview.src = previewUrl;
  characterPreview.hidden = false;
  stageCharacter.src = previewUrl;
  characterDrop.classList.add("has-file");
});
installDropZone(characterDrop, useCharacterFile);

async function decodeTextFile(file) {
  if (!/[.]txt$/i.test(file.name) && file.type !== "text/plain") {
    statusLabel.textContent = "TXTファイルを選択してください";
    return;
  }
  if (file.size > 1024 * 1024) {
    statusLabel.textContent = "TXTファイルは1MB以内にしてください";
    return;
  }
  const bytes = new Uint8Array(await file.arrayBuffer());
  let text = new TextDecoder("utf-8", {fatal: false}).decode(bytes);
  if (text.includes("\uFFFD")) text = new TextDecoder("shift_jis").decode(bytes);
  narrationText.value = text.replace(/^\uFEFF/, "").replace(/\r\n?/g, "\n").trim();
  textFileName.textContent = `${file.name} を読み込みました（${narrationText.value.length.toLocaleString()}文字）`;
  textDrop.classList.add("has-file");
  narrationText.dispatchEvent(new Event("input", {bubbles: true}));
}

textFileInput.addEventListener("change", () => {
  const file = textFileInput.files[0];
  if (file) decodeTextFile(file).catch(error => { statusLabel.textContent = `読込エラー: ${error.message}`; });
});
installDropZone(textDrop, file => setDroppedFile(textFileInput, file));

const statusNames = {
  queued: "チャット入力待ち", preparing: "キャラクターを準備中", chatting: "Gemma 4が応答中", synthesizing: "音声を合成中", generating: "映像を生成中",
  playable: "再生可能", completed: "生成完了", failed: "エラー", cancelled: "キャンセル済み"
};

function markSettingsDirty() {
  const button = form.querySelector("button");
  const busy = latestSession && ["chatting", "synthesizing", "generating", "playable"].includes(latestSession.status);
  if (busy) return;
  button.disabled = false;
  button.textContent = sessionId ? "設定を更新" : "キャラクターを設定";
}

form.querySelectorAll("input, select").forEach(control => {
  control.addEventListener("change", markSettingsDirty);
});

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const button = form.querySelector("button");
  button.disabled = true;
  statusLabel.textContent = "モデルと発話用画像を準備中";
  try {
    const response = await fetch("/api/sessions", {method: "POST", body: new FormData(form)});
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || `HTTP ${response.status}`);
    sessionId = data.id;
    nextIndex = 0;
    playingIndex = null;
    playbackStarted = false;
    preloadedIndex = null;
    stageCharacter.hidden = false;
    stageCharacter.classList.add("visible");
    connectEvents();
    narrationText.disabled = false;
    chatForm.querySelector("button").disabled = false;
    statusLabel.textContent = "チャット入力待ち";
    button.textContent = "設定済み";
    narrationText.focus();
  } catch (error) {
    statusLabel.textContent = `エラー: ${error.message}`;
    button.disabled = false;
  }
});

chatForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const text = narrationText.value.trim();
  if (!sessionId || !text) return;
  const button = chatForm.querySelector("button");
  button.disabled = true;
  try {
    const response = await fetch(`/api/sessions/${sessionId}/messages`, {
      method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({text})
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || `HTTP ${response.status}`);
    narrationText.value = "";
    textFileName.textContent = "";
    assistantLive.textContent = "";
    nextIndex = data.chunks.length;
    playingIndex = null;
    playbackStarted = false;
    stageCharacter.hidden = false;
    stageCharacter.classList.add("visible");
    connectEvents();
  } catch (error) {
    statusLabel.textContent = `送信エラー: ${error.message}`;
    button.disabled = false;
  }
});

narrationText.addEventListener("keydown", event => {
  if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {
    event.preventDefault();
    chatForm.requestSubmit();
  }
});

function connectEvents() {
  if (!sessionId) return;
  if (eventSource) eventSource.close();
  eventSource = new EventSource(`/api/sessions/${sessionId}/events`);
  eventSource.addEventListener("session", event => processSession(JSON.parse(event.data)));
  eventSource.onerror = () => poll();
}

async function poll() {
  if (!sessionId) return;
  try {
    const response = await fetch(`/api/sessions/${sessionId}`, {cache: "no-store"});
    const session = await response.json();
    processSession(session);
  } catch (error) {
    statusLabel.textContent = `状態取得エラー: ${error.message}`;
  }
}

function processSession(session) {
  latestSession = session;
  statusLabel.textContent = statusNames[session.status] || session.status;
  if (session.error) statusLabel.textContent += `: ${session.error}`;
  assistantLive.textContent = session.assistant_text || "";
  renderChunks(session.chunks);
  const readyAhead = session.chunks.filter(chunk => chunk.status === "playable" && chunk.index >= nextIndex).length;
  const readyChunks = session.chunks.filter(chunk => chunk.status === "playable" && chunk.index >= nextIndex);
  const bufferedSeconds = readyChunks.reduce((total, chunk) => total + (chunk.duration || 0), 0);
  const gapText = switchGapMs === null ? "" : `・切替 ${Math.round(switchGapMs)}ms`;
  bufferLabel.textContent = `準備済み ${readyAhead}本・${bufferedSeconds.toFixed(1)}秒${gapText}`;
  if (!playbackStarted && readyChunks.length) {
    // Decode the first file while waiting for enough future media.
    loadPlayer(players[activePlayer], readyChunks[0]);
  }
  const enoughCount = readyAhead >= Math.min(session.startup_buffer_chunks, session.chunks.length);
  if (!playbackStarted && enoughCount) {
    playbackStarted = true;
    playNext(session.chunks);
  } else if (playbackStarted && playingIndex === null) {
    playNext(session.chunks);
  }
  preloadFollowing(session.chunks);
  advanceAfterSpeech(session.chunks);
  if (["completed", "failed", "cancelled"].includes(session.status)) {
    form.querySelector("button").disabled = false;
    chatForm.querySelector("button").disabled = false;
    narrationText.disabled = false;
  }
}

function advanceAfterSpeech(chunks) {
  if (playingIndex === null) return;
  const current = chunks.find(item => item.index === playingIndex);
  const following = chunks.find(item => item.index === playingIndex + 1 && item.status === "playable");
  const player = players[activePlayer];
  if (!current?.speech_duration || !following || player.currentTime < current.speech_duration) return;

  // LTX clips have a fixed duration and short utterances are padded with silence.
  // Once the following clip is ready, skip that padding instead of waiting for
  // the current five-second video to end.
  player.pause();
  lastEndedAt = performance.now();
  nextIndex = playingIndex + 1;
  playingIndex = null;
  playNext(chunks);
}

function loadPlayer(player, chunk) {
  const url = `${chunk.video_url}?t=${chunk.video_ready_at || Date.now()}`;
  if (player.dataset.chunkIndex !== String(chunk.index)) {
    player.src = url;
    player.dataset.chunkIndex = String(chunk.index);
    player.load();
  }
}

function playNext(chunks) {
  const chunk = chunks.find(item => item.index === nextIndex && item.status === "playable");
  if (!chunk) return;
  let targetPlayer = activePlayer;
  if (preloadedIndex === chunk.index) targetPlayer = 1 - activePlayer;
  const player = players[targetPlayer];
  loadPlayer(player, chunk);
  players[activePlayer].classList.remove("active");
  player.classList.add("active");
  activePlayer = targetPlayer;
  preloadedIndex = null;
  playingIndex = chunk.index;
  caption.textContent = chunk.text;
  player.play().catch(() => { statusLabel.textContent = "再生ボタンを押してください"; });
  preloadFollowing(chunks);
}

function preloadFollowing(chunks) {
  if (playingIndex === null) return;
  const wanted = playingIndex + 1;
  const chunk = chunks.find(item => item.index === wanted && item.status === "playable");
  if (!chunk || preloadedIndex === wanted) return;
  loadPlayer(players[1 - activePlayer], chunk);
  preloadedIndex = wanted;
}

players.forEach(player => player.addEventListener("ended", () => {
  if (player !== players[activePlayer]) return;
  lastEndedAt = performance.now();
  nextIndex += 1;
  playingIndex = null;
  if (latestSession) playNext(latestSession.chunks);
}));

players.forEach(player => player.addEventListener("timeupdate", () => {
  if (player === players[activePlayer] && latestSession) {
    advanceAfterSpeech(latestSession.chunks);
  }
}));

players.forEach(player => player.addEventListener("playing", () => {
  if (player === players[activePlayer]) {
    stageCharacter.classList.remove("visible");
  }
  if (player === players[activePlayer] && lastEndedAt !== null) {
    switchGapMs = performance.now() - lastEndedAt;
    lastEndedAt = null;
  }
}));

stageCharacter.addEventListener("transitionend", () => {
  if (!stageCharacter.classList.contains("visible")) stageCharacter.hidden = true;
});

function renderChunks(chunks) {
  chunkList.replaceChildren(...chunks.map(chunk => {
    const item = document.createElement("li");
    item.className = chunk.status;
    item.textContent = `${chunk.index + 1}. ${chunk.text} — ${chunk.status}`;
    return item;
  }));
}
