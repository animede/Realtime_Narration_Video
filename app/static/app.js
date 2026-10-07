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
const stageIdle = document.querySelector("#stage-idle");
const stageIdleB = document.querySelector("#stage-idle-b");
const textDrop = document.querySelector("#text-drop");
const textFileInput = document.querySelector("#text-file");
const narrationSource = document.querySelector("#narration-source");
const narrationButton = document.querySelector("#narrate-button");
const narrationText = document.querySelector("#narration-text");
const textFileName = document.querySelector("#text-file-name");
const uiLanguageSelect = document.querySelector("#ui-language");
const uiLanguageForm = document.querySelector("#ui-language-form");
const inputPanel = document.querySelector(".input-panel");
const messages = {
  ja: {
    uiLanguage: "表示言語", tagline: "文章を約5秒ずつ音声化し、生成できた映像から順番に再生します。",
    characterImage: "キャラクター画像", characterPreview: "キャラクタープレビュー", dropImage: "画像をドロップ",
    dropImageHint: "PNG・JPEG・WebP／クリックして選択", sceneDirection: "映像の方向性",
    scenePlaceholder: "落ち着いたスタジオで説明する", videoInstruction: "動画への指示",
    videoInstructionPlaceholder: "例：話の要点で小さくうなずき、最後に微笑む",
    videoInstructionHint: "次に生成する動画へ反映します。空欄なら自動生成します。", actionLevel: "アクション量",
    actionLow: "少なめ（安定重視）", actionMedium: "標準", actionHigh: "多め（表現重視）", characterType: "キャラクター種別",
    characterStandard: "標準（イラスト・3D）", characterPhotoreal: "実写・口動作優先",
    lipSetting: "実写の発話設定", lipNatural: "自然（閉口優先）",
    lipBalanced: "バランス（軽い開口）", lipMedium: "中間1（やや強い）",
    lipMediumStrong: "中間2（強め）", lipStrong: "強い口動作（大きい開口）", videoProfile: "動画プロファイル",
    idleMotionProfile: "アイドル動作（構図）", idleCloseup: "顔アップ（自然な小動作）",
    idleUpperBody: "上半身（動きを抑える）", idleWide: "膝上・全身（安定重視）",
    idleMotionHint: "画像内に写っている範囲を選択してください。キャラクター設定時に反映します。",
    profile16: "16fps・解像度優先", profile20: "20fps・バランス", profile24: "24fps・動き優先",
    profilePeople: "640×384（5:3 人物向け）", profileStable: "576×384（3:2 安定）",
    profilePortrait34: "384×512（3:4 縦型）", profilePortrait35: "384×640（3:5 縦型・実験）",
    profilePortrait916: "288×512（9:16 縦型）",
    videoEngine: "動画エンジン", profileH3: "H3・24fps固定",
    engineH3Hint: "H3は24fps固定・H3専用の解像度のみ。チャンク長はH3の格子（先頭3秒/後続5.8秒）に自動で合わせます。",
    conversationLanguage: "会話言語", languageAuto: "自動（入力に合わせる）", languageJapanese: "日本語",
    languageEnglish: "英語", liveSettingHint: "緑枠：次の生成から即時反映", setupSettingHint: "黄枠：設定ボタンで反映",
    speakerId: "話者ID", videoSeed: "動画seed", chunkSeconds: "チャンク秒数", preloadCount: "先読み数",
    videoSteps: "生成steps", modalityScale: "口動作強調（scale 1.3）", scaleOn: "有効", scaleOff: "無効（高速）",
    idleLiveliness: "待機の動き", idleLively: "活発（動き優先・既定）", idleCalm: "静か（完全ループ）",
    idlePoolSize: "待機動画の本数", idlePool3: "3本（登録が速い）", idlePool4: "4本", idlePool5: "5本（追い生成が減り会話と衝突しにくい）", idlePool6: "6本", idlePool7: "7本（追い生成が最少・ランダム再生）", idlePoolHint: "初期登録は常に3本だけ生成し、待機中に1本ずつ設定数まで積み増します。多いほど追い生成の頻度が下がり、6本以上はランダム順で再生します。",
    cameraLock: "カメラロック", cameraLockOn: "有効（ドリフト固定）", cameraLockOff: "無効（生成のまま）",
    turnAnchorMode: "会話開始画像", turnAnchorSpeaking: "発話アンカー（口動作優先）", turnAnchorIdle: "待機フレーム（連続性優先）",
    turnEndMode: "会話終了姿勢", turnEndFree: "自由（従来・動き優先）", turnEndReturn: "待機ポーズへ戻る（連続性優先）",
    setCharacter: "キャラクターを設定", updateSettings: "設定を更新", configured: "設定済み・再設定", configuring: "設定中…", idleCharacter: "待機中のキャラクター",
    narrationLabel: "朗読させたい文章", narrationPlaceholder: "文章を入力・貼り付け、またはTXTファイルをドロップ",
    selectTextFile: "TXTを選択", narrate: "朗読", idle: "待機中", configuredCharacter: "設定したキャラクター",
    captionPlaceholder: "生成を開始すると、ここに読み上げ内容が表示されます。",
    messagePlaceholder: "テキストを入力・貼り付け。Enterで送信、Shift+Enterで改行。", send: "送信", sendCombined: "送信・朗読", toggleHide: "設定パネルを隠す", toggleShow: "設定パネルを表示", panelWord: "設定", pauseIdle: "待機動画を停止(GPUの追い生成も止まります)", resumeIdle: "待機動画を再開", savePreset: "このキャラクターを保存", presetNamePrompt: "保存名を入力してください(空欄で日時)", presetRestoring: "保存キャラクターを呼び出し中", presetDelete: "削除", presetDeleteConfirm: name => `「${name}」を削除しますか？`,
    inlineVideoInstructionHint: "文頭に［手を上げながら］のように書くと、そのターンだけの動画指示になります。指示部分は読み上げません。",
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
    scenePlaceholder: "Explain in a calm studio", videoInstruction: "Video instruction",
    videoInstructionPlaceholder: "Example: Nod slightly at key points, then smile at the end",
    videoInstructionHint: "Applies to the next speaking video. Leave blank for automatic motion.", actionLevel: "Action level",
    actionLow: "Low (prioritize stability)", actionMedium: "Medium", actionHigh: "High (more expressive)", characterType: "Character type",
    characterStandard: "Standard (illustration / 3D)", characterPhotoreal: "Photorealistic / lip motion",
    lipSetting: "Photorealistic speech", lipNatural: "Natural (prefer closed mouth)",
    lipBalanced: "Balanced (slightly open)", lipMedium: "Intermediate 1 (moderate)",
    lipMediumStrong: "Intermediate 2 (stronger)", lipStrong: "Strong lip motion (wide open)", videoProfile: "Video profile",
    idleMotionProfile: "Idle motion (image framing)", idleCloseup: "Face close-up (natural subtle motion)",
    idleUpperBody: "Upper body (reduced motion)", idleWide: "Knee-up / full body (most stable)",
    idleMotionHint: "Choose how much of the character is visible. Applied when setting the character.",
    profile16: "16 fps / resolution", profile20: "20 fps / balanced", profile24: "24 fps / motion",
    profilePeople: "640×384 (5:3 / people)", profileStable: "576×384 (3:2 / stable)",
    profilePortrait34: "384×512 (3:4 portrait)", profilePortrait35: "384×640 (3:5 portrait / experimental)",
    profilePortrait916: "288×512 (9:16 portrait)",
    videoEngine: "Video engine", profileH3: "H3 / fixed 24 fps",
    engineH3Hint: "H3 is fixed at 24 fps with its own resolution set. Chunk length follows the H3 frame grid automatically (first ~3 s, then ~5.8 s).",
    conversationLanguage: "Conversation language", languageAuto: "Auto (match input)", languageJapanese: "Japanese",
    languageEnglish: "English", liveSettingHint: "Green: applies to the next generation", setupSettingHint: "Yellow: use the settings button",
    speakerId: "Speaker ID", videoSeed: "Video seed", chunkSeconds: "Chunk seconds", preloadCount: "Startup buffer",
    videoSteps: "Video steps", modalityScale: "Mouth emphasis (scale 1.3)", scaleOn: "Enabled", scaleOff: "Disabled (fast)",
    idleLiveliness: "Idle motion", idleLively: "Lively (more motion, default)", idleCalm: "Calm (perfect loop)",
    idlePoolSize: "Idle clip count", idlePool3: "3 (faster setup)", idlePool4: "4", idlePool5: "5 (fewer refreshes, fewer chat conflicts)", idlePool6: "6", idlePool7: "7 (fewest refreshes, random playback)", idlePoolHint: "Setup always generates just 3 clips; the pool then grows one clip at a time while idle. Larger pools refresh less often, and 6+ clips play in random order.",
    cameraLock: "Camera lock", cameraLockOn: "Enabled (pins drift)", cameraLockOff: "Disabled (as generated)",
    turnAnchorMode: "Turn start image", turnAnchorSpeaking: "Speaking anchor (best lip motion)", turnAnchorIdle: "Idle frame (best continuity)",
    turnEndMode: "Turn end pose", turnEndFree: "Free (default, best motion)", turnEndReturn: "Return to idle pose (best continuity)",
    setCharacter: "Set character", updateSettings: "Update settings", configured: "Configured / redo setup", configuring: "Setting up…", idleCharacter: "Idle character",
    narrationLabel: "Text to narrate", narrationPlaceholder: "Type or paste text, or drop a TXT file",
    selectTextFile: "Choose TXT", narrate: "Narrate", idle: "Idle", configuredCharacter: "Configured character",
    captionPlaceholder: "Spoken text will appear here after generation starts.",
    messagePlaceholder: "Type or paste text. Enter sends; Shift+Enter adds a line.", send: "Send", sendCombined: "Send / Narrate", toggleHide: "Hide settings panel", toggleShow: "Show settings panel", panelWord: "Settings", pauseIdle: "Pause idle video (also pauses GPU replenishment)", resumeIdle: "Resume idle video", savePreset: "Save this character", presetNamePrompt: "Preset name (blank = timestamp)", presetRestoring: "Loading saved character", presetDelete: "Delete", presetDeleteConfirm: name => `Delete "${name}"?`,
    inlineVideoInstructionHint: "Start with [raise one hand] to direct that turn's video. The instruction is not spoken.",
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

const toggleSettings = document.querySelector("#toggle-settings");
let settingsHidden = localStorage.getItem("settingsHidden") === "1";

function applySettingsHidden() {
  document.querySelector("main").classList.toggle("settings-hidden", settingsHidden);
  toggleSettings.textContent = (settingsHidden ? "▶ " : "◀ ") + t("panelWord");
  const hint = t(settingsHidden ? "toggleShow" : "toggleHide");
  toggleSettings.title = hint;
  toggleSettings.setAttribute("aria-label", hint);
  // 折りたたみ中は送信ボタンが朗読を兼ねる
  chatForm.querySelector("button").textContent = t(settingsHidden ? "sendCombined" : "send");
}
toggleSettings.addEventListener("click", () => {
  settingsHidden = !settingsHidden;
  localStorage.setItem("settingsHidden", settingsHidden ? "1" : "0");
  applySettingsHidden();
});
applySettingsHidden();

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
  document.querySelectorAll("[data-i18n-aria-label]").forEach(element => {
    element.setAttribute("aria-label", t(element.dataset.i18nAriaLabel));
  });
  document.querySelectorAll("[data-i18n-label]").forEach(element => {
    element.label = t(element.dataset.i18nLabel);
  });
  if (latestSession) processSession(latestSession);
  if (typeof applySettingsHidden === "function" && toggleSettings) applySettingsHidden();
  const settingsButton = form.querySelector('button[type="submit"]');
  if (sessionId && !latestSession?.error) {
    settingsButton.textContent = t("configured");
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
let liveSettingsPromise = Promise.resolve();
let liveSettingsRevision = 0;
// 待機プレイリスト: 全クリップが入力ポーズで始まり終わるので、順次再生の
// 切替は同一ポーズ上で行われる。残りが2本以下になったら裏で1本追い足す。
const idleStages = [stageIdle, stageIdleB];
let activeIdleStage = 0;
let idleQueue = [];
let idleSeen = new Set();
let idlePoolUrls = [];
let idlePoolSize = 3;
let currentIdleSrc = null;
let idleShown = false;
let idleExtendInFlight = false;
let idleAdvances = 0;
let idleLastExtendAdvance = -99;

function absorbIdlePool(session) {
  // 旧セッションの SSE/ポーリング応答が遅れて届くと、作り直す前の待機クリップが
  // 巡回キューへ混入する(再登録のたびに「数回だけ古い待機動画が出る」再発問題の
  // 正体、2026-10-07 特定)。現在のセッション以外のデータは取り込まない。
  if (!session || (session.id && sessionId && session.id !== sessionId)) return;
  (session.idle_videos || []).forEach(url => {
    if (!idleSeen.has(url)) {
      idleSeen.add(url);
      idleQueue.push(`${url}?t=${session.idle_video_ready_at || Date.now()}`);
    }
  });
  if (session.idle_videos && session.idle_videos.length) {
    const stamp = session.idle_video_ready_at || Date.now();
    idlePoolUrls = session.idle_videos.map(url => `${url}?t=${stamp}`);
    // プールが作り直されたら(regenerate-idle 等)、もうサーバに無いクリップを
    // キューから落とす。残すとバッファ済みの旧クリップが数回再生されてしまう。
    const current = new Set(session.idle_videos);
    idleQueue = idleQueue.filter(src => current.has(src.split("?")[0]));
  }
  if (session.idle_pool_size) idlePoolSize = session.idle_pool_size;
}

function resetIdlePool() {
  idleQueue = [];
  idleSeen = new Set();
  idlePoolUrls = [];
  currentIdleSrc = null;
  idleExtendInFlight = false;
  idleFrozen = false;
  idleAdvances = 0;
  idleLastExtendAdvance = -99;
  idleStages.forEach(media => {
    media.pause();
    media.classList.remove("visible");
    media.removeAttribute("src");
    media.load();
    media.hidden = true;
  });
  activeIdleStage = 0;
}

let lastUserActivity = Date.now();
["pointerdown", "keydown"].forEach(type =>
  document.addEventListener(type, () => {
    lastUserActivity = Date.now();
    // 休止中ならクリック/キー入力の瞬間に追い生成を再開する
    // (次のクリップ終了を待たない)。条件はmaybeExtend側で検査される。
    maybeExtendIdlePool();
  }, {passive: true}));
const IDLE_REFRESH_TIMEOUT_MS = 5 * 60 * 1000;

document.addEventListener("visibilitychange", () => {
  // 非表示タブが待機映像の追い生成でGPUを占有し続けないようにする。
  if (document.hidden) {
    if (idleShown) idleStages[activeIdleStage].pause();
  } else if (idleShown && !idleFrozen && !idleManuallyPaused) {
    lastUserActivity = Date.now();
    idleStages[activeIdleStage].play().catch(() => {});
  }
});

function maybeExtendIdlePool() {
  // ユーザー設計: プール1周(idle_pool_size本)につき1本だけリフレッシュする
  // (毎クリップ生成するとアイドル中ずっとGPUが回り続けてしまう。本数を
  // 増やすほど追い生成頻度=会話との衝突確率が下がる)。
  if (!sessionId || idleExtendInFlight) return;
  if (idleManuallyPaused) return;  // 手動停止中は追い生成もしない
  // タブ非表示・5分間無操作のときは新作を作らない(手持ちの巡回再生は続く)。
  if (document.hidden) return;
  if (Date.now() - lastUserActivity > IDLE_REFRESH_TIMEOUT_MS) return;
  if (idleAdvances - idleLastExtendAdvance < idlePoolSize) return;
  idleLastExtendAdvance = idleAdvances;
  idleExtendInFlight = true;
  fetch(`/api/sessions/${sessionId}/idle-pool`, {method: "POST"})
    .then(async response => {
      const data = await response.json();
      if (response.ok) absorbIdlePool(data);
    })
    .catch(() => {})
    .finally(() => { idleExtendInFlight = false; });
}

let idleFrozen = false;
// 手動停止: 再生停止と同時に待機の追い生成(GPU)も止める(ユーザー要望 2026-10-07)。
let idleManuallyPaused = false;
const stagePauseButton = document.querySelector("#stage-pause");
function updateStagePauseButton() {
  stagePauseButton.hidden = !idleShown;
  stagePauseButton.textContent = idleManuallyPaused ? "▶" : "⏸";
  stagePauseButton.title = t(idleManuallyPaused ? "resumeIdle" : "pauseIdle");
}
stagePauseButton.addEventListener("click", () => {
  idleManuallyPaused = !idleManuallyPaused;
  const active = idleStages[activeIdleStage];
  if (idleManuallyPaused) {
    active.pause();
  } else {
    lastUserActivity = Date.now();
    if (idleShown && !idleFrozen && !document.hidden) active.play().catch(() => {});
    maybeExtendIdlePool();
  }
  updateStagePauseButton();
});

function captureTurnAnchor() {
  // 連続性優先モード: 送信瞬間の待機フレームをキャプチャし、待機映像を
  // そのフレームで静止させる(先頭動画が同じポーズから始まる)。
  const data = new FormData(form);
  if (data.get("turn_anchor_mode") !== "idle_frame") return null;
  const active = idleStages[activeIdleStage];
  if (!idleShown || active.readyState < 2 || !active.videoWidth) return null;
  const canvas = document.createElement("canvas");
  canvas.width = active.videoWidth;
  canvas.height = active.videoHeight;
  canvas.getContext("2d").drawImage(active, 0, 0);
  idleStages.forEach(media => media.pause());
  idleFrozen = true;
  return canvas.toDataURL("image/png");
}

function preloadNextIdle() {
  // 再生中に次クリップを裏の要素へ先読みデコードしておく(切替時の
  // 静止待ちをなくす)。
  const upcoming = idleQueue[0];
  if (!upcoming) return;
  const standby = idleStages[1 - activeIdleStage];
  if (standby.getAttribute("src") !== upcoming) {
    standby.src = upcoming;
    standby.load();
  }
}

function swapIdleTo(src) {
  const incoming = idleStages[1 - activeIdleStage];
  const outgoing = idleStages[activeIdleStage];
  currentIdleSrc = src;
  if (incoming.getAttribute("src") !== src) {
    incoming.src = src;
    incoming.load();
  }
  incoming.hidden = false;
  const start = () => {
    if (!idleShown) return;
    // 全クリップが入力ポーズで始まり終わるため、待機同士の切替は
    // フェードなしの瞬時切替が最も自然(0.36秒のディゾルブは「静止した
    // 旧フレーム×動く新クリップ」の二重写りとして知覚される。24fpsで
    // 特に目立つ)。旧クリップは不透明な新クリップの下で外す。
    incoming.style.zIndex = "4";
    outgoing.style.zIndex = "3";
    incoming.style.transition = "none";
    incoming.play().catch(() => {});
    incoming.classList.add("visible");
    void incoming.offsetWidth;  // 反映を強制してからtransitionを戻す
    incoming.style.transition = "";
    outgoing.classList.remove("visible");
    activeIdleStage = idleStages.indexOf(incoming);
    preloadNextIdle();
  };
  if (incoming.readyState >= 2) start();
  else incoming.addEventListener("canplay", start, {once: true});
}

function startIdlePlayback() {
  const next = idleQueue.shift() || currentIdleSrc;
  if (next) swapIdleTo(next);
  maybeExtendIdlePool();
  preloadNextIdle();
}

function advanceIdle() {
  if (!idleShown) return;
  idleAdvances += 1;
  if (idleQueue.length === 0 && idlePoolUrls.length) {
    // 新作待ちの間はプールを巡回再生する(全クリップが同ポーズで始まり
    // 終わるので、どの順で繋いでも切替は自然)。
    idleQueue = idlePoolUrls.filter(src => src !== currentIdleSrc);
    // プールが6本以上のときはランダム順にする(ユーザー発案)。順番再生だと
    // 本数が増えるほど周回パターンが見えやすくなるため。直前クリップは
    // 上の filter で既に除外されている(連続同一は起きない)。
    if (idlePoolUrls.length > 5) {
      for (let i = idleQueue.length - 1; i > 0; i--) {
        const j = Math.floor(Math.random() * (i + 1));
        [idleQueue[i], idleQueue[j]] = [idleQueue[j], idleQueue[i]];
      }
    }
  }
  maybeExtendIdlePool();
  const next = idleQueue.shift();
  if (next) {
    swapIdleTo(next);
  } else {
    const active = idleStages[activeIdleStage];
    active.currentTime = 0;
    active.play().catch(() => {});
  }
}
idleStages.forEach(media => media.addEventListener("ended", advanceIdle));
const liveSettingNames = [
  "concept", "video_instruction", "action_level", "lip_sync_mode", "conversation_language", "voice_id",
  "video_seed", "video_steps", "modality_scale_enabled", "idle_liveliness",
  "camera_lock_enabled", "turn_anchor_mode", "turn_end_mode", "target_chunk_seconds", "startup_buffer_chunks"
];
const profileSizes = {
  "16fps-5x3": [640, 384], "16fps-3x2": [576, 384],
  "16fps-640x480": [640, 480], "16fps-672x416": [672, 416], "16fps-704x416": [704, 416],
  "16fps-portrait-416x672": [416, 672], "16fps-portrait-416x704": [416, 704],
  "16fps-portrait-480x640": [480, 640], "16fps-portrait-480x800": [480, 800], "16fps-800x480": [800, 480],
  "16fps-4x3-resolution": [512, 384], "16fps-portrait-3x4": [384, 512],
  "16fps-portrait": [384, 640],
  "20fps-4x3-balanced": [512, 384], "20fps-640x480": [640, 480], "20fps-704x416": [704, 416],
  "20fps-portrait-480x640": [480, 640], "20fps-portrait-416x704": [416, 704],
  "24fps-640x384": [640, 384], "24fps-704x416": [704, 416],
  "24fps-portrait-384x640": [384, 640], "24fps-portrait-416x704": [416, 704],
  "24fps-3x2": [480, 320], "24fps-portrait": [288, 512],
  "h3-portrait-352x608": [352, 608], "h3-portrait-384x704": [384, 704],
  "h3-landscape-608x352": [608, 352], "h3-landscape-704x384": [704, 384],
  "h3-3x4-384x512": [384, 512], "h3-4x3-512x384": [512, 384],
  "h3-portrait-320x448": [320, 448], "h3-landscape-448x320": [448, 320],
  "h3-3x4-416x544": [416, 544], "h3-4x3-544x416": [544, 416]
};

// --- 動画エンジン選択(LTX-2.5 / MiniMax-H3) ---
// H3 は fps=24 固定・専用の解像度表のみ。エンジンに属さないプロファイルは選択肢から外す。
const engineSelect = document.querySelector("#video-engine");
const engineHint = document.querySelector("#engine-hint");
const engineEyebrow = document.querySelector("#engine-eyebrow");
const chunkSecondsInput = form.querySelector('[name="target_chunk_seconds"]');
let h3DefaultProfile = "h3-portrait-352x608";
let defaultLtxProfile = "20fps-4x3-balanced";

function applyEngine() {
  const engine = engineSelect.value;
  profileSelect.querySelectorAll("optgroup[data-engine]").forEach(group => {
    const active = group.dataset.engine === engine;
    group.hidden = !active;
    group.disabled = !active;
  });
  const selected = profileSelect.selectedOptions[0];
  if (!selected || selected.parentElement.dataset.engine !== engine) {
    profileSelect.value = engine === "h3" ? h3DefaultProfile : defaultLtxProfile;
  }
  engineHint.hidden = engine !== "h3";
  engineEyebrow.textContent = engine === "h3" ? "MiniMax-H3 / AivisSpeech" : "LTX-2.5 / AivisSpeech";
  // H3 のチャンク長はサーバが格子に合わせて決める(フォームの値は使わない)
  chunkSecondsInput.disabled = engine === "h3";
  applyAspectRatio();
}

fetch("/api/config").then(response => response.json()).then(config => {
  h3DefaultProfile = config.h3?.default_profile || h3DefaultProfile;
  // 新規セッションの既定エンジンはサーバ設定(VIDEO_ENGINE)。復元済みセッションは触らない。
  if (!sessionId && config.default_engine && engineSelect.value !== config.default_engine) {
    engineSelect.value = config.default_engine;
    applyEngine();
    refreshPresets();
  }
}).catch(() => {});

function applyAspectRatio() {
  const [width, height] = profileSizes[profileSelect.value];
  videoStack.style.aspectRatio = `${width} / ${height}`;
  document.querySelector(".player-panel").classList.toggle("portrait", height > width);
}
profileSelect.addEventListener("change", applyAspectRatio);
engineSelect.addEventListener("change", () => { applyEngine(); refreshPresets(); });
applyEngine();
applyLanguage();

function setDroppedFile(input, file) {
  const transfer = new DataTransfer();
  transfer.items.add(file);
  input.files = transfer.files;
  input.dispatchEvent(new Event("change", {bubbles: true}));
}

// 枠外ドロップでブラウザがファイルを開いてページ遷移するのを防ぐ
["dragover", "drop"].forEach(type => window.addEventListener(type, event => event.preventDefault()));

function installDropZone(zone, onFile, {allowUrl = false} = {}) {
  ["dragenter", "dragover"].forEach(type => zone.addEventListener(type, event => {
    event.preventDefault();
    zone.classList.add("drag-over");
  }));
  ["dragleave", "drop"].forEach(type => zone.addEventListener(type, event => {
    event.preventDefault();
    zone.classList.remove("drag-over");
  }));
  zone.addEventListener("drop", async event => {
    const file = event.dataTransfer.files[0];
    if (file) return onFile(file);
    // 他タブの画像やファイルマネージャは File が無く URL だけ来ることがある
    const url = (event.dataTransfer.getData("text/uri-list") ||
                 event.dataTransfer.getData("text/plain") || "").split("\n")[0].trim();
    if (!url || !allowUrl) return;
    try {
      let resp = null;
      if (!url.startsWith("file:")) {
        try {
          resp = await fetch(url, {mode: "cors"});
          if (!resp.ok) throw new Error(resp.status);
        } catch { resp = null; }
      }
      if (!resp) {
        resp = await fetch(`/api/fetch-image?url=${encodeURIComponent(url)}`);
        if (!resp.ok) throw new Error((await resp.json().catch(() => null))?.detail || resp.status);
      }
      const blob = await resp.blob();
      const name = decodeURIComponent(url.split("/").pop().split("?")[0]) || "dropped.png";
      onFile(new File([blob], name, {type: blob.type}));
    } catch (error) {
      statusLabel.textContent = t("error", String(error.message || error));
    }
  });
}

let previewUrl = null;
function useCharacterFile(file) {
  const typeOk = file.type.startsWith("image/") || !file.type;
  if (!typeOk || !/[.](png|jpe?g|webp)$/i.test(file.name)) {
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
  resetIdlePool();
  stageCharacter.hidden = false;
  stageCharacter.classList.add("visible");
  characterDrop.classList.add("has-file");
});
installDropZone(characterDrop, useCharacterFile, {allowUrl: true});

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
  const button = form.querySelector('button[type="submit"]');
  const busy = latestSession && ["chatting", "synthesizing", "generating", "playable"].includes(latestSession.status);
  settingsDirty = true;
  button.disabled = Boolean(busy);
  button.textContent = sessionId ? t("configured") : t("setCharacter");
}

form.querySelectorAll(".setup-setting input, .setup-setting select").forEach(control => {
  control.addEventListener("change", markSettingsDirty);
});

function liveSettingsPayload() {
  const data = new FormData(form);
  return Object.fromEntries(liveSettingNames.map(name => [name, data.get(name)]));
}

function syncLiveSettings() {
  if (!sessionId) return Promise.resolve();
  const payload = liveSettingsPayload();
  const revision = ++liveSettingsRevision;
  inputPanel.classList.add("live-settings-saving");
  inputPanel.classList.remove("live-settings-error");
  liveSettingsPromise = liveSettingsPromise.catch(() => {}).then(async () => {
    const response = await fetch(`/api/sessions/${sessionId}/settings`, {
      method: "PATCH", headers: {"Content-Type": "application/json"}, body: JSON.stringify(payload)
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || `HTTP ${response.status}`);
    if (revision === liveSettingsRevision) inputPanel.classList.remove("live-settings-saving");
    return data;
  }).catch(error => {
    if (revision === liveSettingsRevision) {
      inputPanel.classList.remove("live-settings-saving");
      inputPanel.classList.add("live-settings-error");
      statusLabel.textContent = t("error", error.message);
    }
    throw error;
  });
  return liveSettingsPromise;
}

form.querySelectorAll(".live-setting input, .live-setting select, .live-setting textarea").forEach(control => {
  control.addEventListener("change", () => { syncLiveSettings().catch(() => {}); });
});

function adoptSession(data) {
  sessionId = data.id;
  try { localStorage.setItem("narrationSessionId", sessionId); } catch {}
  liveSettingsRevision = 0;
  liveSettingsPromise = Promise.resolve();
  inputPanel.classList.remove("live-settings-saving", "live-settings-error");
  settingsDirty = false;
  nextIndex = (data.chunks || []).length;
  playingIndex = null;
  playbackStarted = false;
  preloadedIndex = null;
  resetIdlePool();
  absorbIdlePool(data);
  showIdleStage();
  connectEvents();
  narrationText.disabled = false;
  chatForm.querySelector("button").disabled = false;
  narrationButton.disabled = false;
  statusLabel.textContent = t("queued");
  const setupButton = form.querySelector('button[type="submit"]');
  setupButton.textContent = t("configured");
  setupButton.disabled = false;  // 「設定済み・再設定」として押下可能のまま
  document.querySelector("#save-preset").hidden = !data.character_prepared;
}

// --- キャラクタープリセット(保存・一覧・復元・削除) ---
const presetStrip = document.querySelector("#preset-strip");
const savePresetButton = document.querySelector("#save-preset");

function applyPresetSettings(settings) {
  // エンジンを先に反映(プロファイルの選択肢がエンジンごとに異なるため)
  engineSelect.value = (settings || {}).video_engine || "ltx25";
  applyEngine();
  Object.entries(settings || {}).forEach(([key, value]) => {
    const control = form.querySelector(`[name="${key}"]`);
    if (control) control.value = String(value);
  });
  applyAspectRatio();
}

async function refreshPresets() {
  try {
    // プリセットはエンジン別(LTX のアイドルプールは H3 では使えない)。選択中のエンジンのみ一覧する。
    const response = await fetch(`/api/presets?engine=${encodeURIComponent(engineSelect.value)}`);
    const presets = await response.json();
    presetStrip.textContent = "";
    presetStrip.hidden = presets.length === 0;
    presets.forEach(preset => {
      const item = document.createElement("span");
      item.className = "preset-item";
      const image = document.createElement("img");
      image.src = preset.thumbnail_url;
      image.title = `${preset.name}（クリックで呼び出し）`;
      image.addEventListener("click", () => { restorePreset(preset.id); });
      const label = document.createElement("span");
      label.className = "preset-name";
      label.textContent = preset.name;
      const remove = document.createElement("button");
      remove.type = "button";
      remove.className = "preset-delete";
      remove.textContent = "×";
      remove.title = t("presetDelete");
      remove.addEventListener("click", async () => {
        if (!confirm(t("presetDeleteConfirm", preset.name))) return;
        await fetch(`/api/presets/${preset.id}`, {method: "DELETE"});
        refreshPresets();
      });
      item.append(image, remove, label);
      presetStrip.append(item);
    });
  } catch { /* 一覧の取得失敗は致命的ではない */ }
}

async function restorePreset(presetId) {
  statusLabel.textContent = t("presetRestoring");
  try {
    const response = await fetch(`/api/presets/${presetId}/restore`, {method: "POST"});
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || `HTTP ${response.status}`);
    applyPresetSettings(data);
    adoptSession(data);
  } catch (error) {
    statusLabel.textContent = t("error", error.message);
  }
}

savePresetButton.addEventListener("click", async () => {
  if (!sessionId) return;
  const name = prompt(t("presetNamePrompt"), "");
  if (name === null) return;
  savePresetButton.disabled = true;
  try {
    const response = await fetch("/api/presets", {
      method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify({session_id: sessionId, name})
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || `HTTP ${response.status}`);
    refreshPresets();
  } catch (error) {
    statusLabel.textContent = t("error", error.message);
  } finally {
    savePresetButton.disabled = false;
  }
});
refreshPresets();

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const button = form.querySelector('button[type="submit"]');
  button.disabled = true;
  button.textContent = t("configuring");
  statusLabel.textContent = t("preparingModel");
  // 登録の await 中(数分)に旧セッションの SSE が待機プールを再注入しないよう、
  // 先に旧セッションから切り離して巡回を空にする(ドロップ済みの静止画が表示される)。
  // 失敗時は旧セッションへ再接続して復帰する。
  const previousSessionId = sessionId;
  if (eventSource) { eventSource.close(); eventSource = null; }
  sessionId = null;
  resetIdlePool();
  try {
    const response = await fetch("/api/sessions", {method: "POST", body: new FormData(form)});
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || `HTTP ${response.status}`);
    adoptSession(data);
    narrationText.focus();
  } catch (error) {
    statusLabel.textContent = t("error", error.message);
    button.disabled = false;
    sessionId = previousSessionId;
    if (sessionId) {
      button.textContent = t("configured");
      connectEvents();
      poll();
    } else {
      button.textContent = t("setCharacter");
    }
  }
});

async function runNarration() {
  const text = narrationSource.value.trim();
  if (!sessionId || !text) return;
  narrationButton.disabled = true;
  chatForm.querySelector("button").disabled = true;
  try {
    await syncLiveSettings();
    const turnAnchor = captureTurnAnchor();
    const response = await fetch(`/api/sessions/${sessionId}/narrations`, {
      method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify({text, turn_anchor: turnAnchor})
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || `HTTP ${response.status}`);
    nextIndex = data.chunks.length;
    playingIndex = null;
    playbackStarted = false;
    assistantLive.textContent = "";
    showIdleStage();
    connectEvents();
  } catch (error) {
    statusLabel.textContent = t("sendError", error.message);
    narrationButton.disabled = false;
    chatForm.querySelector("button").disabled = false;
  }
}
narrationButton.addEventListener("click", () => { runNarration(); });

chatForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const text = narrationText.value.trim();
  if (!sessionId) return;
  if (!text) {
    // 兼用モード: 会話入力が空なら朗読文章を読む。両方空なら何もしない。
    if (settingsHidden && narrationSource.value.trim()) await runNarration();
    return;
  }
  const button = chatForm.querySelector("button");
  button.disabled = true;
  narrationButton.disabled = true;
  try {
    await syncLiveSettings();
    const turnAnchor = captureTurnAnchor();
    const response = await fetch(`/api/sessions/${sessionId}/messages`, {
      method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify({text, turn_anchor: turnAnchor})
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || `HTTP ${response.status}`);
    narrationText.value = "";
    assistantLive.textContent = "";
    nextIndex = data.chunks.length;
    playingIndex = null;
    playbackStarted = false;
    showIdleStage();
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
  // 旧セッション宛の遅延イベントを丸ごと破棄(absorbIdlePool と同じ理由)。
  if (!session || (session.id && sessionId && session.id !== sessionId)) return;
  latestSession = session;
  absorbIdlePool(session);
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
    idleFrozen = false;
    form.querySelector('button[type="submit"]').disabled = false;
    chatForm.querySelector("button").disabled = false;
    narrationButton.disabled = false;
    narrationText.disabled = false;
  }
  if (playingIndex === null && !readyChunks.length && session.character_prepared) showIdleStage();
  restoreCharacterAfterTurn(session);
}

function showIdleStage() {
  const active = idleStages[activeIdleStage];
  const hasIdleVideo = Boolean(active.getAttribute("src")) || idleQueue.length > 0;
  stageCharacter.hidden = hasIdleVideo;
  stageCharacter.classList.toggle("visible", !hasIdleVideo);
  idleShown = hasIdleVideo;
  if (!hasIdleVideo) { updateStagePauseButton(); return; }
  if (!active.getAttribute("src")) {
    startIdlePlayback();
    return;
  }
  active.hidden = false;
  if (!active.classList.contains("visible") && active.readyState > 0) {
    active.currentTime = 0;
  }
  active.classList.add("visible");
  if (!idleFrozen && !idleManuallyPaused) active.play().catch(() => {});
  else if (idleManuallyPaused) active.pause();
  updateStagePauseButton();
}

function hideIdleStage() {
  idleShown = false;
  idleFrozen = false;
  stageCharacter.classList.remove("visible");
  idleStages.forEach(media => media.classList.remove("visible"));
  updateStagePauseButton();
}

function restoreCharacterAfterTurn(session) {
  if (session.status !== "completed" || playingIndex !== null || nextIndex < session.chunks.length) return;
  showIdleStage();
}

function advanceAfterSpeech(chunks) {
  if (playingIndex === null) return;
  const current = chunks.find(item => item.index === playingIndex);
  const player = players[activePlayer];
  if (!current?.speech_duration || player.currentTime < current.speech_duration) return;

  // LTX clips have a fixed duration and short utterances are padded with silence.
  // Stop at the real audio boundary even when the next clip is not ready. The
  // generated idle loop deterministically hides any open mouth in the silent tail.
  player.pause();
  lastEndedAt = performance.now();
  nextIndex = playingIndex + 1;
  playingIndex = null;
  const following = chunks.find(item => item.index === nextIndex && item.status === "playable");
  if (following) {
    playNext(chunks);
  } else {
    showIdleStage();
  }
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
  // advanceAfterSpeech(発話境界)が先に進めていたら二重前進しない。
  // 発話が動画尺いっぱいのチャンクでは両者がほぼ同時に発火し、
  // nextIndexが2つ進んでチャンクを1つ飛ばすレースがあった(2026-09-14)。
  if (playingIndex === null) return;
  lastEndedAt = performance.now();
  nextIndex = playingIndex + 1;
  playingIndex = null;
  if (latestSession) {
    playNext(latestSession.chunks);
    if (playingIndex === null) showIdleStage();
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
    hideIdleStage();
  }
  if (player === players[activePlayer] && lastEndedAt !== null) {
    switchGapMs = performance.now() - lastEndedAt;
    lastEndedAt = null;
  }
}));

[stageCharacter, stageIdle, stageIdleB].forEach(media => media.addEventListener("transitionend", () => {
  if (!media.classList.contains("visible")) {
    media.hidden = true;
    if (media !== stageCharacter) media.pause();
  }
}));

function renderChunks(chunks) {
  chunkList.replaceChildren(...chunks.map(chunk => {
    const item = document.createElement("li");
    item.className = chunk.status;
    item.textContent = `${chunk.index + 1}. ${chunk.text} — ${t(chunk.status)} `;
    if (["playable", "completed", "played"].includes(chunk.status) && sessionId) {
      for (const [suffix, label] of [["video", "MP4"], ["audio", "WAV"]]) {
        const a = document.createElement("a");
        a.href = `/api/sessions/${sessionId}/chunks/${chunk.index}/${suffix}?download=1`;
        a.setAttribute("download", "");
        a.className = "chunk-dl";
        a.textContent = label;
        item.appendChild(a);
      }
    }
    return item;
  }));
}


// --- 前回セッションの復元(リロード後も生成済みチャンクへ辿れるように) ---
(async () => {
  if (sessionId) return;
  let saved = null;
  try { saved = localStorage.getItem("narrationSessionId"); } catch {}
  if (!saved) return;
  try {
    const response = await fetch(`/api/sessions/${saved}`);
    if (!response.ok) throw new Error(String(response.status));
    const data = await response.json();
    // 復元セッションのエンジン・解像度をフォームへ反映(プロファイル選択肢はエンジン別)
    engineSelect.value = data.video_engine || "ltx25";
    applyEngine();
    if (data.video_profile && profileSizes[data.video_profile]) profileSelect.value = data.video_profile;
    applyAspectRatio();
    refreshPresets();
    adoptSession(data);
    renderChunks(data.chunks || []);
    statusLabel.textContent = t("configured");
  } catch {
    try { localStorage.removeItem("narrationSessionId"); } catch {}
  }
})();
