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
const narrationSource = document.querySelector("#narration-source");
const narrationButton = document.querySelector("#narrate-button");
const narrationText = document.querySelector("#narration-text");
const textFileName = document.querySelector("#text-file-name");
const uiLanguageSelect = document.querySelector("#ui-language");
const uiLanguageForm = document.querySelector("#ui-language-form");
const messages = {
  ja: {
    uiLanguage: "表示言語", tagline: "文章を約5秒ずつ音声化し、生成できた映像から順番に再生します。",
    characterImage: "キャラクター画像", characterPreview: "キャラクタープレビュー", dropImage: "画像をドロップ",
    dropImageHint: "PNG・JPEG・WebP／クリックして選択", sceneDirection: "映像の方向性",
    scenePlaceholder: "落ち着いたスタジオで説明する", characterType: "キャラクター種別",
    characterStandard: "標準（イラスト・3D）", characterPhotoreal: "実写・口動作優先",
    lipSetting: "実写の発話設定", lipFast: "高速（口開き画像を使用）",
    lipStrong: "口動作優先（会話もmodality 1.3）", videoProfile: "動画プロファイル",
    profile16: "16fps・解像度優先", profile20: "20fps・バランス", profile24: "24fps・動き優先",
    profilePeople: "640×384（5:3 人物向け）", profileStable: "576×384（3:2 安定）",
    profilePortrait34: "384×512（3:4 縦型）", profilePortrait35: "384×640（3:5 縦型・実験）",
    profilePortrait916: "288×512（9:16 縦型）",
    conversationLanguage: "会話言語", languageAuto: "自動（入力に合わせる）", languageJapanese: "日本語",
    languageEnglish: "英語", speakerId: "話者ID", videoSeed: "動画seed", chunkSeconds: "チャンク秒数", preloadCount: "先読み数",
    setCharacter: "キャラクターを設定", updateSettings: "設定を更新", configured: "設定済み",
    narrationLabel: "朗読させたい文章", narrationPlaceholder: "文章を入力・貼り付け、またはTXTファイルをドロップ",
    selectTextFile: "TXTを選択", narrate: "朗読", idle: "待機中", configuredCharacter: "設定したキャラクター",
    captionPlaceholder: "生成を開始すると、ここに読み上げ内容が表示されます。",
    messagePlaceholder: "テキストを入力・貼り付け。Enterで送信、Shift+Enterで改行。", send: "送信",
    queued: "チャット入力待ち", preparing: "キャラクターを準備中", chatting: "Gemma 4が応答中",
    synthesizing: "音声を合成中", generating: "映像を生成中", playable: "再生可能", completed: "生成完了",
    failed: "エラー", cancelled: "キャンセル済み", preparingModel: "モデルと発話用画像を準備中",
    imageTypeError: "PNG・JPEG・WebP画像を選択してください", textTypeError: "TXTファイルを選択してください",
    textSizeError: "TXTファイルは1MB以内にしてください", loadedFile: name => `${name} を読み込みました`,
    loadError: value => `読込エラー: ${value}`, error: value => `エラー: ${value}`,
    sendError: value => `送信エラー: ${value}`, pollError: value => `状態取得エラー: ${value}`,
    buffer: (count, seconds) => `準備済み ${count}本・${seconds}秒`, switchGap: ms => `・切替 ${ms}ms`,
    playRequired: "再生ボタンを押してください"
  },
  en: {
    uiLanguage: "Display language", tagline: "Speech is generated in roughly five-second chunks and completed videos play in order.",
    characterImage: "Character image", characterPreview: "Character preview", dropImage: "Drop an image",
    dropImageHint: "PNG, JPEG, or WebP / click to select", sceneDirection: "Scene direction",
    scenePlaceholder: "Explain in a calm studio", characterType: "Character type",
    characterStandard: "Standard (illustration / 3D)", characterPhotoreal: "Photorealistic / lip motion",
    lipSetting: "Photorealistic speech", lipFast: "Fast (use open-mouth anchor)",
    lipStrong: "Strong lip motion (modality 1.3 in chat)", videoProfile: "Video profile",
    profile16: "16 fps / resolution", profile20: "20 fps / balanced", profile24: "24 fps / motion",
    profilePeople: "640×384 (5:3 / people)", profileStable: "576×384 (3:2 / stable)",
    profilePortrait34: "384×512 (3:4 portrait)", profilePortrait35: "384×640 (3:5 portrait / experimental)",
    profilePortrait916: "288×512 (9:16 portrait)",
    conversationLanguage: "Conversation language", languageAuto: "Auto (match input)", languageJapanese: "Japanese",
    languageEnglish: "English", speakerId: "Speaker ID", videoSeed: "Video seed", chunkSeconds: "Chunk seconds", preloadCount: "Startup buffer",
    setCharacter: "Set character", updateSettings: "Update settings", configured: "Configured",
    narrationLabel: "Text to narrate", narrationPlaceholder: "Type or paste text, or drop a TXT file",
    selectTextFile: "Choose TXT", narrate: "Narrate", idle: "Idle", configuredCharacter: "Configured character",
    captionPlaceholder: "Spoken text will appear here after generation starts.",
    messagePlaceholder: "Type or paste text. Enter sends; Shift+Enter adds a line.", send: "Send",
    queued: "Ready for chat", preparing: "Preparing character", chatting: "Gemma 4 is responding",
    synthesizing: "Synthesizing speech", generating: "Generating video", playable: "Playable", completed: "Generation complete",
    failed: "Error", cancelled: "Cancelled", preparingModel: "Preparing the model and speaking anchor",
    imageTypeError: "Select a PNG, JPEG, or WebP image.", textTypeError: "Select a TXT file.",
    textSizeError: "TXT files must be no larger than 1 MB.", loadedFile: name => `Loaded ${name}`,
    loadError: value => `Read error: ${value}`, error: value => `Error: ${value}`,
    sendError: value => `Send error: ${value}`, pollError: value => `Status error: ${value}`,
    buffer: (count, seconds) => `${count} ready / ${seconds}s`, switchGap: ms => ` / switch ${ms}ms`,
    playRequired: "Press the play button to continue"
  }
};
let uiLanguage = localStorage.getItem("uiLanguage") || (navigator.language.startsWith("ja") ? "ja" : "en");
if (!messages[uiLanguage]) uiLanguage = "ja";

function t(key, ...args) {
  const value = messages[uiLanguage][key] ?? messages.ja[key] ?? key;
  return typeof value === "function" ? value(...args) : value;
}

function applyLanguage() {
  document.documentElement.lang = uiLanguage;
  uiLanguageSelect.value = uiLanguage;
  uiLanguageForm.value = uiLanguage;
  document.querySelectorAll("[data-i18n]").forEach(element => {
    element.textContent = t(element.dataset.i18n);
  });
  document.querySelectorAll("[data-i18n-placeholder]").forEach(element => {
    element.placeholder = t(element.dataset.i18nPlaceholder);
  });
  document.querySelectorAll("[data-i18n-alt]").forEach(element => {
    element.alt = t(element.dataset.i18nAlt);
  });
  document.querySelectorAll("[data-i18n-label]").forEach(element => {
    element.label = t(element.dataset.i18nLabel);
  });
  if (latestSession) processSession(latestSession);
  const settingsButton = form.querySelector("button");
  if (sessionId && !latestSession?.error) {
    settingsButton.textContent = t(settingsDirty ? "updateSettings" : "configured");
  }
}

uiLanguageSelect.addEventListener("change", () => {
  uiLanguage = uiLanguageSelect.value;
  localStorage.setItem("uiLanguage", uiLanguage);
  applyLanguage();
});
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
let settingsDirty = false;
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
applyLanguage();

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
    statusLabel.textContent = t("imageTypeError");
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
    statusLabel.textContent = t("textTypeError");
    return;
  }
  if (file.size > 1024 * 1024) {
    statusLabel.textContent = t("textSizeError");
    return;
  }
  const bytes = new Uint8Array(await file.arrayBuffer());
  let text = new TextDecoder("utf-8", {fatal: false}).decode(bytes);
  if (text.includes("\uFFFD")) text = new TextDecoder("shift_jis").decode(bytes);
  narrationSource.value = text.replace(/^\uFEFF/, "").replace(/\r\n?/g, "\n").trim();
  textFileName.textContent = `${t("loadedFile", file.name)} (${narrationSource.value.length.toLocaleString()} chars)`;
  textDrop.classList.add("has-file");
  narrationSource.dispatchEvent(new Event("input", {bubbles: true}));
}

textFileInput.addEventListener("change", () => {
  const file = textFileInput.files[0];
  if (file) decodeTextFile(file).catch(error => { statusLabel.textContent = t("loadError", error.message); });
});
installDropZone(textDrop, file => setDroppedFile(textFileInput, file));

function markSettingsDirty() {
  const button = form.querySelector("button");
  const busy = latestSession && ["chatting", "synthesizing", "generating", "playable"].includes(latestSession.status);
  if (busy) return;
  settingsDirty = true;
  button.disabled = false;
  button.textContent = sessionId ? t("updateSettings") : t("setCharacter");
}

form.querySelectorAll("input, select").forEach(control => {
  control.addEventListener("change", markSettingsDirty);
});

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const button = form.querySelector("button");
  button.disabled = true;
  statusLabel.textContent = t("preparingModel");
  try {
    const response = await fetch("/api/sessions", {method: "POST", body: new FormData(form)});
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || `HTTP ${response.status}`);
    sessionId = data.id;
    settingsDirty = false;
    nextIndex = 0;
    playingIndex = null;
    playbackStarted = false;
    preloadedIndex = null;
    stageCharacter.hidden = false;
    stageCharacter.classList.add("visible");
    connectEvents();
    narrationText.disabled = false;
    chatForm.querySelector("button").disabled = false;
    narrationButton.disabled = false;
    statusLabel.textContent = t("queued");
    button.textContent = t("configured");
    narrationText.focus();
  } catch (error) {
    statusLabel.textContent = t("error", error.message);
    button.disabled = false;
  }
});

narrationButton.addEventListener("click", async () => {
  const text = narrationSource.value.trim();
  if (!sessionId || !text) return;
  narrationButton.disabled = true;
  chatForm.querySelector("button").disabled = true;
  try {
    const response = await fetch(`/api/sessions/${sessionId}/narrations`, {
      method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({text})
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || `HTTP ${response.status}`);
    nextIndex = data.chunks.length;
    playingIndex = null;
    playbackStarted = false;
    assistantLive.textContent = "";
    stageCharacter.hidden = false;
    stageCharacter.classList.add("visible");
    connectEvents();
  } catch (error) {
    statusLabel.textContent = t("sendError", error.message);
    narrationButton.disabled = false;
    chatForm.querySelector("button").disabled = false;
  }
});

chatForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const text = narrationText.value.trim();
  if (!sessionId || !text) return;
  const button = chatForm.querySelector("button");
  button.disabled = true;
  narrationButton.disabled = true;
  try {
    const response = await fetch(`/api/sessions/${sessionId}/messages`, {
      method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({text})
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || `HTTP ${response.status}`);
    narrationText.value = "";
    assistantLive.textContent = "";
    nextIndex = data.chunks.length;
    playingIndex = null;
    playbackStarted = false;
    stageCharacter.hidden = false;
    stageCharacter.classList.add("visible");
    connectEvents();
  } catch (error) {
    statusLabel.textContent = t("sendError", error.message);
    button.disabled = false;
    narrationButton.disabled = false;
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
    statusLabel.textContent = t("pollError", error.message);
  }
}

function processSession(session) {
  latestSession = session;
  statusLabel.textContent = t(session.status);
  if (session.error) statusLabel.textContent += `: ${session.error}`;
  assistantLive.textContent = session.assistant_text || "";
  renderChunks(session.chunks);
  const readyAhead = session.chunks.filter(chunk => chunk.status === "playable" && chunk.index >= nextIndex).length;
  const readyChunks = session.chunks.filter(chunk => chunk.status === "playable" && chunk.index >= nextIndex);
  const bufferedSeconds = readyChunks.reduce((total, chunk) => total + (chunk.duration || 0), 0);
  const gapText = switchGapMs === null ? "" : t("switchGap", Math.round(switchGapMs));
  bufferLabel.textContent = `${t("buffer", readyAhead, bufferedSeconds.toFixed(1))}${gapText}`;
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
    narrationButton.disabled = false;
    narrationText.disabled = false;
  }
  restoreCharacterAfterTurn(session);
}

function restoreCharacterAfterTurn(session) {
  if (session.status !== "completed" || playingIndex !== null || nextIndex < session.chunks.length) return;
  stageCharacter.hidden = false;
  stageCharacter.classList.add("visible");
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
  player.play().catch(() => { statusLabel.textContent = t("playRequired"); });
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
  if (latestSession) {
    playNext(latestSession.chunks);
    restoreCharacterAfterTurn(latestSession);
  }
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
    item.textContent = `${chunk.index + 1}. ${chunk.text} — ${t(chunk.status)}`;
    return item;
  }));
}
