/**
 * Sunrise Hotel Frontend Voice Client
 * Direct Interactive Voice Pipeline on Port 8004 (English en-IN).
 * Powered by Sarvam Saaras v4 STT, LangGraph, and Sarvam Bulbul v3 TTS.
 * 
 * Features:
 * 1. OS-Level Device Prediction & Auto-Detection (Bluetooth, Headset, Speaker, Mic).
 * 2. 100% Hands-Free Auto-Detection of Sentence Start and Sentence Stop.
 * 3. Dynamic Rising Speech Volume Meter.
 */

// Global State
let isCallActive = false;
let isListening = false;
let isDirectRecording = false;
let mediaStream = null;
let mediaRecorder = null;
let recordedChunks = [];
let audioContext = null;
let analyser = null;
let audioSourceNode = null;
let animFrameId = null;
let activeAudioPlayer = null;

// Hardware Device State
let selectedDeviceId = "auto";
let predictedDeviceLabel = "Detecting...";
let predictedDeviceType = "Headset";

// Real-Time Hands-Free Sentence VAD State
let ambientNoiseFloor = 4.0;
let isSpeakingSentence = false;
let speechOnsetTimestamp = 0;
let consecutiveSilenceFrames = 0;
let consecutiveSpeechFrames = 0;
let speechRecognitionAssistant = null;

// Multilingual Session State (English, Tamil, Tanglish)
let currentSessionLanguage = "auto";

function formatLanguageName(lang) {
  if (!lang) return "EN";
  const l = lang.toLowerCase();
  if (l.includes("ta") || l.includes("tamil")) return "தமிழ்";
  if (l.includes("tanglish")) return "Tanglish";
  return "EN";
}

function updateLanguageBadge(lang) {
  const badgeText = document.getElementById("currentLangText");
  if (!badgeText) return;
  const l = (lang || "").toLowerCase();
  if (l.includes("ta") || l.includes("tamil")) {
    badgeText.innerText = "Tamil (தமிழ்)";
  } else if (l.includes("tanglish")) {
    badgeText.innerText = "Tanglish (தமிழ் + English)";
  } else if (l.includes("en")) {
    badgeText.innerText = "English (en-IN)";
  }
}

// ==============================================================================
// Voice Service / Port 8004 Status Checker
// ==============================================================================

async function checkVoiceServiceStatus() {
  const dot = document.getElementById("listenPortDot");
  const text = document.getElementById("listenPortText");
  const badge = document.getElementById("listenPortBadge");

  try {
    const res = await fetch("/voice/status");
    if (res.ok) {
      const data = await res.json();
      if (dot) dot.className = "w-2 h-2 mr-1.5 rounded-full bg-emerald-400 animate-pulse";
      if (text) text.innerText = `Listen Port ${data.port}: Ready`;
      if (badge) {
        badge.className = "inline-flex items-center px-3 py-1 rounded-full text-xs font-semibold bg-emerald-950/80 text-emerald-400 border border-emerald-700/60 shadow-sm";
      }
    } else {
      throw new Error(`HTTP ${res.status}`);
    }
  } catch (err) {
    if (dot) dot.className = "w-2 h-2 mr-1.5 rounded-full bg-red-400";
    if (text) text.innerText = "Listen Port 8004: Offline";
    if (badge) {
      badge.className = "inline-flex items-center px-3 py-1 rounded-full text-xs font-semibold bg-red-950/80 text-red-400 border border-red-700/60 shadow-sm";
    }
  }
}

// ==============================================================================
// OS-Level Device Prediction & Auto-Detection Algorithm
// (Headphones, Bluetooth, External Mics, System Default)
// ==============================================================================

async function autoDetectAndSelectDevice(showNotification = false) {
  if (!navigator.mediaDevices || !navigator.mediaDevices.enumerateDevices) return;

  try {
    const devices = await navigator.mediaDevices.enumerateDevices();
    const audioInputs = devices.filter((d) => d.kind === "audioinput");
    if (audioInputs.length === 0) return;

    let bestDevice = null;
    let highestScore = -1;
    let detectedType = "Microphone";
    let iconClass = "fa-solid fa-microphone";

    for (const dev of audioInputs) {
      const label = (dev.label || "").toLowerCase();
      let score = 10;
      let type = "Microphone";
      let icon = "fa-solid fa-microphone";

      // Rank 1: Bluetooth Headsets / Earbuds (e.g., AirPods, Buds, Wireless)
      if (
        label.includes("bluetooth") ||
        label.includes("airpod") ||
        label.includes("buds") ||
        label.includes("wireless") ||
        label.includes("hands-free") ||
        label.includes("neckband")
      ) {
        score = 100;
        type = "Bluetooth";
        icon = "fa-brands fa-bluetooth text-blue-400";
      }
      // Rank 2: Headset / Headphone Microphones (e.g. "Headset Microphone (Realtek(R) Audio)")
      else if (
        label.includes("headset") ||
        label.includes("headphone") ||
        label.includes("earphone") ||
        (label.includes("realtek") && label.includes("headset"))
      ) {
        score = 80;
        type = "Headset";
        icon = "fa-solid fa-headphones text-emerald-400";
      }
      // Rank 3: Dedicated External USB Microphones
      else if (
        label.includes("usb") ||
        label.includes("fifine") ||
        label.includes("blue yeti") ||
        label.includes("rode") ||
        label.includes("shure")
      ) {
        score = 60;
        type = "USB Mic";
        icon = "fa-solid fa-microphone-lines text-amber-400";
      }
      // Rank 4: System Default Device
      else if (dev.deviceId === "default") {
        score = 40;
        type = "Default OS";
        icon = "fa-solid fa-desktop text-slate-400";
      }
      // Rank 5: Internal Laptop Mic Array (deprioritized)
      else if (
        label.includes("array") ||
        label.includes("internal") ||
        label.includes("built-in") ||
        label.includes("integrated")
      ) {
        score = 20;
        type = "Internal Mic";
        icon = "fa-solid fa-laptop text-slate-400";
      }

      if (score > highestScore) {
        highestScore = score;
        bestDevice = dev;
        detectedType = type;
        iconClass = icon;
      }
    }

    if (bestDevice) {
      if (selectedDeviceId === "auto" || !selectedDeviceId) {
        selectedDeviceId = bestDevice.deviceId;
      }
      predictedDeviceLabel = bestDevice.label || `${detectedType} (Device)`;
      predictedDeviceType = detectedType;

      updatePredictedDeviceUI(bestDevice, detectedType, iconClass);

      if (showNotification) {
        showDeviceNotification(`Auto-Switched to: ${predictedDeviceLabel}`);
      }
    }

    populateMicrophoneList(audioInputs);
  } catch (err) {
    console.warn("Device prediction warning:", err);
  }
}

function updatePredictedDeviceUI(device, type, iconClass) {
  const nameEl = document.getElementById("predictedDeviceName");
  const badgeEl = document.getElementById("predictedDeviceBadge");
  const iconEl = document.getElementById("predictedDeviceIcon");

  if (nameEl) nameEl.innerText = device.label || `${type} (Connected)`;
  if (badgeEl) badgeEl.innerText = type;
  if (iconEl) iconEl.innerHTML = `<i class="${iconClass}"></i>`;
}

function populateMicrophoneList(audioInputs) {
  const select = document.getElementById("micSelect");
  if (!select) return;

  select.innerHTML = "";

  // Auto-Predicted option
  const autoOpt = document.createElement("option");
  autoOpt.value = "auto";
  autoOpt.text = `⚡ Auto: ${predictedDeviceType}`;
  select.appendChild(autoOpt);

  if (audioInputs && audioInputs.length > 0) {
    audioInputs.forEach((d, idx) => {
      const opt = document.createElement("option");
      opt.value = d.deviceId;
      opt.text = d.label || `Microphone ${idx + 1}`;
      if (d.deviceId === selectedDeviceId && selectedDeviceId !== "auto") {
        opt.selected = true;
      }
      select.appendChild(opt);
    });
  }
}

async function onSelectMicrophone(deviceId) {
  if (deviceId === "auto") {
    selectedDeviceId = "auto";
    await autoDetectAndSelectDevice(true);
  } else {
    selectedDeviceId = deviceId;
    console.log("User manually selected device:", deviceId);
  }

  // If call is active, seamlessly switch to the newly chosen device
  if (isCallActive) {
    try {
      if (mediaStream) mediaStream.getTracks().forEach((t) => t.stop());
      mediaStream = await getMicrophoneStream();
      await setupAudioVisualizer(mediaStream);
      startListeningTurn();
    } catch (e) {
      console.error("Failed to switch audio stream:", e);
    }
  }
}

async function getMicrophoneStream() {
  const audioConstraints = {
    echoCancellation: true,
    noiseSuppression: false, // Prevent aggressive gating from muffling headset voice
    autoGainControl: true,
  };

  if (selectedDeviceId && selectedDeviceId !== "auto" && selectedDeviceId !== "default") {
    audioConstraints.deviceId = { exact: selectedDeviceId };
  }

  try {
    return await navigator.mediaDevices.getUserMedia({ audio: audioConstraints });
  } catch (e) {
    console.warn("Retrying with standard audio constraints:", e);
    return await navigator.mediaDevices.getUserMedia({ audio: true });
  }
}

// OS-Level Hardware Change Listener (Plugging in Headset / Bluetooth)
if (navigator.mediaDevices && typeof navigator.mediaDevices.addEventListener === "function") {
  navigator.mediaDevices.addEventListener("devicechange", async () => {
    console.log("OS Audio Device Change detected! Re-predicting audio hardware...");
    await autoDetectAndSelectDevice(true);

    if (isCallActive) {
      try {
        if (mediaStream) mediaStream.getTracks().forEach((t) => t.stop());
        mediaStream = await getMicrophoneStream();
        await setupAudioVisualizer(mediaStream);
        startListeningTurn();
      } catch (e) {
        console.warn("Stream re-route on devicechange failed:", e);
      }
    }
  });
}

function showDeviceNotification(msg) {
  const badge = document.getElementById("voiceActivityBadge");
  const text = document.getElementById("voiceActivityText");
  if (badge && text) {
    text.innerText = `🎧 ${msg}`;
    setTimeout(() => {
      if (!isCallActive) {
        text.innerText = "Microphone: Standby (Click 'Start Call')";
      }
    }, 3000);
  }
}

// ==============================================================================
// Voice Call Lifecycle (Driven by the Main Center Button)
// ==============================================================================

async function toggleConnection() {
  ensureAudioContextActive();

  if (isCallActive) {
    endVoiceCall();
  } else {
    await startVoiceCall();
  }
}

async function startVoiceCall() {
  updateStatus("connecting", "Starting Call...");
  setVoiceActivityStatus("initializing", "Requesting microphone access...");

  try {
    // 1. Auto-predict & request the optimal microphone (Bluetooth / Headset / Realtek)
    mediaStream = await getMicrophoneStream();

    // 2. Discover and update device lists
    await autoDetectAndSelectDevice(false);

    // 3. Setup Web Audio API analyser for live volume meter & waveform
    await setupAudioVisualizer(mediaStream);

    isCallActive = true;
    updateStatus("connected", "Online & Listening");

    // 4. Play Maya's initial English greeting
    await playInitialGreeting();

    // 5. Start active hands-free listening turn
    startListeningTurn();

  } catch (err) {
    console.error("Microphone access failed:", err);
    updateStatus("error", "Microphone Error");
    setVoiceActivityStatus("error", "Microphone access blocked or unavailable.");
    alert("Microphone Error: " + (err.message || err) + "\n\nPlease click the lock icon in the address bar and allow microphone access.");
    handleDisconnectedState();
  }
}

async function playInitialGreeting() {
  updateStatusText("Maya is greeting...");
  setVoiceActivityStatus("agent_speaking", "Maya is speaking greeting...");
  setAgentSpeaking(true);

  try {
    const res = await fetch("/voice/greeting");
    if (res.ok) {
      const data = await res.json();
      if (data.text) {
        appendTranscript("agent", data.text);
      }
      if (data.audio_base64) {
        await playBase64Audio(data.audio_base64);
      }
    }
  } catch (e) {
    console.warn("Greeting fetch warning:", e);
  } finally {
    setAgentSpeaking(false);
  }
}

function startListeningTurn() {
  if (!isCallActive || !mediaStream) return;

  ensureAudioContextActive();

  // Reset Hands-Free Sentence Detection state
  isSpeakingSentence = false;
  speechOnsetTimestamp = 0;
  consecutiveSilenceFrames = 0;
  consecutiveSpeechFrames = 0;
  recordedChunks = [];

  // Start OS WebSpeech assistant in parallel for instant sentence boundary detection
  startWebSpeechAssistant();

  // Initialize MediaRecorder
  try {
    const mimeType = MediaRecorder.isTypeSupported("audio/webm;codecs=opus")
      ? "audio/webm;codecs=opus"
      : (MediaRecorder.isTypeSupported("audio/webm") ? "audio/webm" : "");

    mediaRecorder = mimeType ? new MediaRecorder(mediaStream, { mimeType }) : new MediaRecorder(mediaStream);
  } catch (e) {
    console.warn("MediaRecorder creation fallback:", e);
    try {
      mediaRecorder = new MediaRecorder(mediaStream);
    } catch (err) {
      console.error("Fatal MediaRecorder error:", err);
      return;
    }
  }

  mediaRecorder.ondataavailable = (e) => {
    if (e.data && e.data.size > 0) {
      recordedChunks.push(e.data);
    }
  };

  mediaRecorder.onstop = async () => {
    isListening = false;
    stopWebSpeechAssistant();

    if (recordedChunks.length > 0 && isCallActive) {
      const mime = mediaRecorder.mimeType || "audio/webm";
      const audioBlob = new Blob(recordedChunks, { type: mime });
      await processGuestAudio(audioBlob);
    }
  };

  // Start recording in 200ms slices
  mediaRecorder.start(200);
  isListening = true;
  const langPrompt = (currentSessionLanguage === "ta-IN" || currentSessionLanguage === "tamil")
    ? "Listening... தமிழில் பேசுங்கள்"
    : (currentSessionLanguage === "tanglish" ? "Listening... Tanglish-la பேசுங்கள்" : "Listening... Speak in English, தமிழ், or Tanglish");
  updateStatusText(langPrompt);
  setVoiceActivityStatus("listening", `🎧 ${langPrompt} (Hands-Free auto-detect)`);
  setVisualizerActive(true);
}

function stopListeningTurn() {
  if (mediaRecorder && mediaRecorder.state !== "inactive") {
    try {
      mediaRecorder.stop();
    } catch (e) {
      console.warn("Error stopping MediaRecorder:", e);
    }
  }
  isListening = false;
  stopWebSpeechAssistant();
}

// Manual send button (Optional instant shortcut)
function manualFinishSpeaking() {
  if (isListening && mediaRecorder && mediaRecorder.state !== "inactive") {
    setVoiceActivityStatus("processing", "Sending speech to Maya...");
    stopListeningTurn();
  }
}

// ==============================================================================
// OS-Level WebSpeech Assistant (Parallel Sentence Boundary Detector)
// ==============================================================================

function startWebSpeechAssistant() {
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SpeechRecognition) return;

  try {
    stopWebSpeechAssistant();
    const r = new SpeechRecognition();
    r.continuous = false;
    r.interimResults = true;
    if (currentSessionLanguage === "ta-IN" || currentSessionLanguage === "tamil") {
      r.lang = "ta-IN";
    } else {
      r.lang = "en-IN";
    }

    r.onspeechstart = () => {
      if (!isSpeakingSentence) {
        isSpeakingSentence = true;
        speechOnsetTimestamp = Date.now();
        consecutiveSilenceFrames = 0;
        setVoiceActivityStatus("speaking", "🎙️ Speech detected — listening to your sentence...");
      }
    };

    // Native OS sentence boundary detection
    r.onspeechend = () => {
      console.log("[WebSpeech OS] Sentence completion detected natively by browser!");
      if (isCallActive && isListening && isSpeakingSentence) {
        isSpeakingSentence = false;
        setVoiceActivityStatus("processing", "✨ Sentence finished! Submitting to Maya...");
        stopListeningTurn();
      }
    };

    r.onresult = (evt) => {
      for (let i = evt.resultIndex; i < evt.results.length; i++) {
        if (evt.results[i].isFinal) {
          console.log("[WebSpeech OS] Final sentence segment:", evt.results[i][0].transcript);
          if (isCallActive && isListening) {
            isSpeakingSentence = false;
            setVoiceActivityStatus("processing", "✨ Sentence finished! Submitting to Maya...");
            stopListeningTurn();
            return;
          }
        }
      }
    };

    r.onerror = () => {
      // Speech errors are safely ignored; audio energy VAD acts as the guaranteed baseline
    };

    r.start();
    speechRecognitionAssistant = r;
  } catch (e) {
    console.debug("WebSpeech assistant note:", e);
  }
}

function stopWebSpeechAssistant() {
  if (speechRecognitionAssistant) {
    try {
      speechRecognitionAssistant.abort();
    } catch (e) {}
    speechRecognitionAssistant = null;
  }
}

// ==============================================================================
// Process Speech Turn with Backend Sarvam STT -> LangGraph -> TTS
// ==============================================================================

async function processGuestAudio(audioBlob) {
  updateStatusText("⏳ Maya is processing your speech...");
  setVoiceActivityStatus("processing", "Transcribing & processing speech with Sarvam STT...");
  setVisualizerActive(false);
  resetVolumeMeter();

  try {
    const formData = new FormData();
    const ext = audioBlob.type.includes("wav") ? "wav" : "webm";
    formData.append("audio_file", audioBlob, `speech.${ext}`);

    const resp = await fetch("/voice/chat", {
      method: "POST",
      body: formData,
    });

    if (!resp.ok) {
      throw new Error(`Server returned HTTP ${resp.status}`);
    }

    const data = await resp.json();

    if (!data.success) {
      updateStatusText(data.error || "No speech recognized. Please speak again.");
      setVoiceActivityStatus("waiting", data.error || "Speech not recognized. Please speak clearly in English, Tamil, or Tanglish.");
      if (isCallActive) {
        setTimeout(() => {
          if (isCallActive) startListeningTurn();
        }, 1200);
      }
      return;
    }

    // Update active conversation language
    if (data.language) {
      currentSessionLanguage = data.language;
      updateLanguageBadge(data.language);
    }

    // 1. Display guest transcript
    if (data.user_text) {
      appendTranscript("guest", data.user_text, formatLanguageName(data.language));
    }

    // 2. Display Maya's reply
    if (data.reply_text) {
      appendTranscript("agent", data.reply_text, formatLanguageName(data.language));
    }

    // 3. Update reservation card
    if (data.slots) {
      updateReservationCard(data.slots);
      if (data.slots.booking_confirmed && data.slots.confirmation_code) {
        showBookingConfirmation(data.slots.confirmation_code, data.slots.total_price);
      }
    }

    // 4. Play Maya's voice response using Sarvam Bulbul v3
    if (data.audio_base64) {
      updateStatusText("🔊 Maya is speaking...");
      setVoiceActivityStatus("agent_speaking", "Maya is speaking...");
      setAgentSpeaking(true);
      await playBase64Audio(data.audio_base64);
      setAgentSpeaking(false);
    }

    // 5. Automatically resume hands-free listening for the next turn
    if (isCallActive) {
      startListeningTurn();
    }

  } catch (err) {
    console.error("Audio turn processing error:", err);
    updateStatusText("Error: " + (err.message || err));
    setVoiceActivityStatus("error", "Error connecting to backend: " + (err.message || err));
    if (isCallActive) {
      setTimeout(() => {
        if (isCallActive) startListeningTurn();
      }, 1800);
    }
  }
}

function playBase64Audio(b64) {
  return new Promise((resolve) => {
    if (activeAudioPlayer) {
      activeAudioPlayer.pause();
    }
    const audio = new Audio("data:audio/wav;base64," + b64);
    activeAudioPlayer = audio;

    // Route audio to predicted output sink if supported
    if (typeof audio.setSinkId === "function" && selectedDeviceId && selectedDeviceId !== "auto") {
      audio.setSinkId("default").catch(() => {});
    }

    audio.onended = () => {
      activeAudioPlayer = null;
      resolve();
    };
    audio.onerror = () => {
      activeAudioPlayer = null;
      resolve();
    };
    audio.play().catch((e) => {
      console.warn("Audio autoplay blocked by browser:", e);
      resolve();
    });
  });
}

function endVoiceCall() {
  isCallActive = false;
  isListening = false;
  stopListeningTurn();

  if (activeAudioPlayer) {
    activeAudioPlayer.pause();
    activeAudioPlayer = null;
  }

  if (mediaStream) {
    mediaStream.getTracks().forEach((t) => t.stop());
    mediaStream = null;
  }

  if (animFrameId) {
    cancelAnimationFrame(animFrameId);
    animFrameId = null;
  }

  if (audioContext && audioContext.state !== "closed") {
    audioContext.close().catch(() => {});
    audioContext = null;
  }

  handleDisconnectedState();
}

function handleDisconnectedState() {
  isCallActive = false;
  isListening = false;
  updateStatus("disconnected", "Offline");
  setVisualizerActive(false);
  setAgentSpeaking(false);
  resetVolumeMeter();
  setVoiceActivityStatus("standby", "Microphone: Standby (Click 'Start Call')");
}

// ==============================================================================
// Real-Time Audio Visualizer & Adaptive Hands-Free Sentence VAD
// ==============================================================================

async function ensureAudioContextActive() {
  if (audioContext && audioContext.state === "suspended") {
    try {
      await audioContext.resume();
      console.log("AudioContext active, state:", audioContext.state);
    } catch (e) {
      console.warn("AudioContext resume warning:", e);
    }
  }
}

async function setupAudioVisualizer(stream) {
  try {
    if (!audioContext || audioContext.state === "closed") {
      audioContext = new (window.AudioContext || window.webkitAudioContext)();
    }

    if (audioContext.state === "suspended") {
      await audioContext.resume();
    }

    if (audioSourceNode) {
      try { audioSourceNode.disconnect(); } catch (e) {}
    }

    audioSourceNode = audioContext.createMediaStreamSource(stream);
    analyser = audioContext.createAnalyser();
    analyser.fftSize = 256;
    analyser.smoothingTimeConstant = 0.2;
    audioSourceNode.connect(analyser);

    const frequencyData = new Uint8Array(analyser.frequencyBinCount);
    const timeDomainData = new Uint8Array(analyser.fftSize);
    const bars = document.querySelectorAll("#visualizer span");

    function renderAudioFrame() {
      if (!isCallActive && !isDirectRecording) {
        resetVolumeMeter();
        return;
      }
      animFrameId = requestAnimationFrame(renderAudioFrame);

      if (audioContext && audioContext.state === "suspended") {
        audioContext.resume().catch(() => {});
      }

      // 1. Calculate frequency energy
      analyser.getByteFrequencyData(frequencyData);
      let freqSum = 0;
      let freqMax = 0;
      for (let i = 0; i < frequencyData.length; i++) {
        freqSum += frequencyData[i];
        if (frequencyData[i] > freqMax) freqMax = frequencyData[i];
      }
      const freqAvg = freqSum / frequencyData.length;

      // 2. Compute RMS Volume from time domain data
      analyser.getByteTimeDomainData(timeDomainData);
      let sumSquares = 0;
      for (let i = 0; i < timeDomainData.length; i++) {
        const normalized = (timeDomainData[i] - 128) / 128;
        sumSquares += normalized * normalized;
      }
      const rms = Math.sqrt(sumSquares / timeDomainData.length);

      // 3. Combined sensitive volume metric (0-100 scale)
      const rmsLevel = rms * 380;
      const freqAvgLevel = (freqAvg / 128) * 100;
      const freqPeakLevel = (freqMax / 255) * 85;
      const rawLevel = Math.max(rmsLevel, freqAvgLevel * 1.3, freqPeakLevel);
      const volumeLevel = Math.min(100, Math.round(rawLevel));

      // 4. Update the Rising Volume Bar & Label in real time
      updateRisingVolumeUI(volumeLevel);

      // 5. Update frequency wave bars dynamically
      bars.forEach((bar, idx) => {
        const val = frequencyData[idx % frequencyData.length];
        const h = Math.max(4, Math.min(36, (val / 255) * 42));
        bar.style.height = `${h}px`;
        if (volumeLevel >= Math.max(8, ambientNoiseFloor + 4)) {
          bar.classList.remove("bg-amber-400");
          bar.classList.add("bg-emerald-400");
        } else {
          bar.classList.remove("bg-emerald-400");
          bar.classList.add("bg-amber-400");
        }
      });

      // 6. Intelligent Hands-Free Turn Detection (Sentence Start & Sentence Stop)
      if (isCallActive && isListening && !activeAudioPlayer) {
        handleHandsFreeSentenceVAD(volumeLevel);
      }
    }

    renderAudioFrame();
  } catch (e) {
    console.warn("Visualizer setup error:", e);
  }
}

function updateRisingVolumeUI(level) {
  const bar = document.getElementById("voiceLevelBar");
  const valLabel = document.getElementById("voiceLevelValue");
  const micIcon = document.getElementById("micInputIcon");

  if (bar) {
    bar.style.width = `${level}%`;
  }

  const threshold = Math.max(8, Math.round(ambientNoiseFloor + 4));

  if (valLabel) {
    if (level >= threshold) {
      valLabel.innerText = `${level}% (Speaking...)`;
      valLabel.className = "font-mono text-xs font-bold text-emerald-400 animate-pulse";
      if (micIcon) micIcon.className = "fa-solid fa-microphone-lines text-emerald-400";
    } else {
      valLabel.innerText = `${level}% (Silence)`;
      valLabel.className = "font-mono text-xs font-semibold text-slate-400";
      if (micIcon) micIcon.className = "fa-solid fa-microphone-lines text-slate-500";
    }
  }
}

function resetVolumeMeter() {
  const bar = document.getElementById("voiceLevelBar");
  const valLabel = document.getElementById("voiceLevelValue");
  const micIcon = document.getElementById("micInputIcon");
  if (bar) bar.style.width = "0%";
  if (valLabel) {
    valLabel.innerText = "0% (Silence)";
    valLabel.className = "font-mono text-xs font-semibold text-slate-400";
  }
  if (micIcon) micIcon.className = "fa-solid fa-microphone-lines text-slate-500";

  const bars = document.querySelectorAll("#visualizer span");
  bars.forEach((b) => (b.style.height = "4px"));
}

/**
 * 100% Hands-Free Sentence Boundary Detection:
 * - Dynamically tracks ambient noise floor.
 * - Detects speech onset (start of sentence).
 * - Detects sentence completion (stop of sentence after ~800ms natural pause).
 * - Automatically submits the audio without requiring ANY manual button click!
 */
function handleHandsFreeSentenceVAD(volumeLevel) {
  const now = Date.now();

  // Continuously calibrate ambient noise floor during silence
  if (!isSpeakingSentence) {
    ambientNoiseFloor = ambientNoiseFloor * 0.96 + volumeLevel * 0.04;
  }

  // Dynamic hysteresis thresholds based on ambient noise floor
  const onsetThreshold = Math.max(9, Math.round(ambientNoiseFloor + 5));
  const offsetThreshold = Math.max(5, Math.round(ambientNoiseFloor + 2.5));

  if (volumeLevel >= onsetThreshold) {
    consecutiveSpeechFrames++;
    consecutiveSilenceFrames = 0;

    // After 2 consecutive frames of voice (>35ms), lock speech onset
    if (consecutiveSpeechFrames >= 2) {
      if (!isSpeakingSentence) {
        isSpeakingSentence = true;
        speechOnsetTimestamp = now;
        console.log(`[VAD] Speech onset detected! (Level: ${volumeLevel}%, Baseline: ${ambientNoiseFloor.toFixed(1)}%)`);
      }
      setVoiceActivityStatus("speaking", `🎙️ Speaking sentence (${volumeLevel}%) — listening...`);
    }
  } else if (volumeLevel <= offsetThreshold) {
    consecutiveSilenceFrames++;
    consecutiveSpeechFrames = 0;

    if (isSpeakingSentence) {
      const sentenceDuration = now - speechOnsetTimestamp;
      const silenceDurationMs = consecutiveSilenceFrames * 16.6; // ~16.6ms per 60fps frame

      // If user has spoken at least 350ms and has paused for ~800ms
      if (sentenceDuration >= 350) {
        if (silenceDurationMs >= 800) {
          console.log(`[VAD] Sentence completion detected! (Silence ${Math.round(silenceDurationMs)}ms, Speech ${sentenceDuration}ms). Auto-sending...`);
          isSpeakingSentence = false;
          consecutiveSilenceFrames = 0;
          setVoiceActivityStatus("processing", "✨ Sentence finished! Submitting to Maya...");
          stopListeningTurn();
        } else {
          const remainingPct = Math.min(100, Math.round((silenceDurationMs / 800) * 100));
          setVoiceActivityStatus("pause", `⏳ Sentence ending... Auto-submitting (${remainingPct}%)`);
        }
      }
    }
  }
}

// ==============================================================================
// Voice Activity Diagnostic Status Bar
// ==============================================================================

function setVoiceActivityStatus(state, msg) {
  const badge = document.getElementById("voiceActivityBadge");
  const dot = document.getElementById("voiceActivityDot");
  const text = document.getElementById("voiceActivityText");

  if (!badge || !dot || !text) return;
  text.innerText = msg;

  if (state === "speaking") {
    badge.className = "mt-3 px-3 py-1 rounded-full text-xs font-medium border bg-emerald-950/80 text-emerald-300 border-emerald-600/70 shadow level-glow transition-all";
    dot.className = "w-2 h-2 rounded-full bg-emerald-400 animate-ping";
  } else if (state === "listening") {
    badge.className = "mt-3 px-3 py-1 rounded-full text-xs font-medium border bg-blue-950/60 text-blue-300 border-blue-700/60 transition-all";
    dot.className = "w-2 h-2 rounded-full bg-blue-400 animate-pulse";
  } else if (state === "pause") {
    badge.className = "mt-3 px-3 py-1 rounded-full text-xs font-medium border bg-teal-950/70 text-teal-300 border-teal-600/70 transition-all";
    dot.className = "w-2 h-2 rounded-full bg-teal-400 animate-pulse";
  } else if (state === "processing") {
    badge.className = "mt-3 px-3 py-1 rounded-full text-xs font-medium border bg-amber-950/60 text-amber-300 border-amber-600/70 transition-all";
    dot.className = "w-2 h-2 rounded-full bg-amber-400 animate-spin";
  } else if (state === "agent_speaking") {
    badge.className = "mt-3 px-3 py-1 rounded-full text-xs font-medium border bg-purple-950/60 text-purple-300 border-purple-600/70 transition-all";
    dot.className = "w-2 h-2 rounded-full bg-purple-400 animate-pulse";
  } else if (state === "error") {
    badge.className = "mt-3 px-3 py-1 rounded-full text-xs font-medium border bg-red-950/60 text-red-300 border-red-700/60 transition-all";
    dot.className = "w-2 h-2 rounded-full bg-red-400";
  } else {
    badge.className = "mt-3 px-3 py-1 rounded-full text-xs font-medium border bg-slate-800/80 text-slate-400 border-slate-700/80 transition-all";
    dot.className = "w-2 h-2 rounded-full bg-slate-500";
  }
}

// ==============================================================================
// Direct Input-Bar Mic Button
// ==============================================================================

let directMediaStream = null;
let directMediaRecorder = null;
let directChunks = [];

async function toggleDirectVoiceRecord() {
  ensureAudioContextActive();

  const btn = document.getElementById("recordVoiceBtn");
  const icon = document.getElementById("recordVoiceIcon");
  const statusMsg = document.getElementById("voiceStatusMsg");

  if (isDirectRecording) {
    if (directMediaRecorder && directMediaRecorder.state !== "inactive") {
      directMediaRecorder.stop();
    }
    isDirectRecording = false;
    if (btn) btn.className = "w-10 h-10 rounded-xl bg-slate-800 hover:bg-slate-700 border border-slate-700 text-amber-400 flex items-center justify-center flex-shrink-0 transition-all shadow";
    if (icon) icon.className = "fa-solid fa-microphone text-sm";
    if (statusMsg) statusMsg.classList.add("hidden");
  } else {
    try {
      directMediaStream = await getMicrophoneStream();
      await setupAudioVisualizer(directMediaStream);

      directChunks = [];
      directMediaRecorder = new MediaRecorder(directMediaStream);

      directMediaRecorder.ondataavailable = (e) => {
        if (e.data && e.data.size > 0) directChunks.push(e.data);
      };

      directMediaRecorder.onstop = async () => {
        if (directMediaStream) {
          directMediaStream.getTracks().forEach((t) => t.stop());
          directMediaStream = null;
        }
        if (directChunks.length > 0) {
          const blob = new Blob(directChunks, { type: "audio/webm" });
          await processGuestAudio(blob);
        }
      };

      directMediaRecorder.start();
      isDirectRecording = true;

      if (btn) btn.className = "w-10 h-10 rounded-xl bg-red-600 hover:bg-red-500 text-white flex items-center justify-center flex-shrink-0 transition-all shadow animate-pulse";
      if (icon) icon.className = "fa-solid fa-stop text-sm";
      if (statusMsg) {
        statusMsg.innerText = "🎙️ Recording... Speak in English, தமிழ், or Tanglish, then click Stop.";
        statusMsg.classList.remove("hidden");
      }
      setVoiceActivityStatus("speaking", "Recording speech from input mic...");
      setVisualizerActive(true);
    } catch (err) {
      console.error("Direct record error:", err);
      alert("Microphone Error: " + (err.message || err));
    }
  }
}

// ==============================================================================
// UI State Updates
// ==============================================================================

function updateStatus(state, message) {
  const statusDot = document.getElementById("statusDot");
  const statusText = document.getElementById("statusText");
  const micButton = document.getElementById("micButton");
  const micLabel = document.getElementById("micLabel");
  const micIcon = document.getElementById("micIcon");

  if (state === "connected") {
    if (statusDot) statusDot.className = "w-2 h-2 mr-2 rounded-full bg-emerald-400 animate-pulse";
    if (statusText) statusText.innerText = "Online & Listening";
    if (micButton) micButton.className = "relative z-10 w-28 h-28 rounded-full bg-gradient-to-tr from-emerald-500 to-teal-500 flex flex-col items-center justify-center shadow-2xl hover:scale-105 active:scale-95 transition-all text-white border-4 border-slate-900";
    if (micIcon) micIcon.className = "fa-solid fa-phone-slash text-3xl";
    if (micLabel) micLabel.innerText = "End Call";
  } else if (state === "connecting") {
    if (statusDot) statusDot.className = "w-2 h-2 mr-2 rounded-full bg-amber-400 animate-ping";
    if (statusText) statusText.innerText = message || "Connecting...";
    if (micButton) micButton.className = "relative z-10 w-28 h-28 rounded-full bg-gradient-to-tr from-amber-600 to-amber-400 flex flex-col items-center justify-center shadow-2xl text-white border-4 border-slate-900";
    if (micIcon) micIcon.className = "fa-solid fa-spinner fa-spin text-3xl";
    if (micLabel) micLabel.innerText = "Connecting";
  } else {
    if (statusDot) statusDot.className = "w-2 h-2 mr-2 rounded-full bg-slate-500";
    if (statusText) statusText.innerText = message || "Offline";
    if (micButton) micButton.className = "relative z-10 w-28 h-28 rounded-full bg-gradient-to-tr from-amber-500 to-orange-500 flex flex-col items-center justify-center shadow-2xl hover:scale-105 active:scale-95 transition-all text-white border-4 border-slate-900 group";
    if (micIcon) micIcon.className = "fa-solid fa-microphone text-3xl group-hover:scale-110 transition-transform";
    if (micLabel) micLabel.innerText = "Start Call";
  }
}

function updateStatusText(msg) {
  const statusSubtitle = document.getElementById("agentStatusSubtitle");
  if (statusSubtitle) {
    statusSubtitle.innerText = msg;
  }
}

function setVisualizerActive(active) {
  const v = document.getElementById("visualizer");
  if (v) {
    v.style.opacity = active ? "1" : "0.3";
  }
}

function setAgentSpeaking(speaking) {
  const ring = document.getElementById("orbRing");
  const title = document.getElementById("agentStatusTitle");

  if (speaking) {
    if (ring) {
      ring.className = "absolute w-36 h-36 rounded-full bg-purple-500/30 anim-pulse";
      ring.classList.remove("hidden");
    }
    if (title) title.innerText = "Maya is speaking...";
  } else {
    if (ring) ring.classList.add("hidden");
    if (title) title.innerText = isCallActive ? "Maya is listening..." : "Receptionist Maya is ready";
  }
}

function appendTranscript(speaker, text, lang = null) {
  const box = document.getElementById("transcriptBox");
  if (!box || !text) return;

  const isAgent = speaker === "agent";
  const row = document.createElement("div");
  row.className = `flex items-start space-x-3 ${isAgent ? "" : "flex-row-reverse space-x-reverse"}`;

  const avatarBg = isAgent ? "bg-amber-500/20 text-amber-400" : "bg-blue-500/20 text-blue-400";
  const bubbleBg = isAgent ? "bg-slate-800/80 border border-slate-700/60 text-slate-200" : "bg-blue-600 text-white";
  const avatarLetter = isAgent ? "M" : "U";

  let badge = "";
  if (lang) {
    badge = `<span class="text-[9px] px-1.5 py-0.5 rounded bg-slate-900/60 text-slate-400 font-mono">${lang}</span>`;
  }

  row.innerHTML = `
    <div class="w-7 h-7 rounded-lg ${avatarBg} flex items-center justify-center flex-shrink-0 text-xs font-bold">${avatarLetter}</div>
    <div class="${bubbleBg} rounded-2xl ${isAgent ? 'rounded-tl-none' : 'rounded-tr-none'} p-3 max-w-[85%] text-xs shadow">
      <div class="flex items-center justify-between mb-1">
        <span class="font-semibold text-[11px] ${isAgent ? 'text-amber-400' : 'text-blue-200'}">${isAgent ? 'Maya (Receptionist)' : 'You'}</span>
        ${badge}
      </div>
      <div>${text}</div>
    </div>
  `;

  box.appendChild(row);
  box.scrollTop = box.scrollHeight;
}

function clearTranscript() {
  const box = document.getElementById("transcriptBox");
  if (box) box.innerHTML = "";
}

function updateReservationCard(slots) {
  if (!slots) return;
  if (slots.guest_name) document.getElementById("slotGuestName").innerText = slots.guest_name;
  if (slots.guest_phone) document.getElementById("slotPhone").innerText = slots.guest_phone;
  if (slots.room_type) document.getElementById("slotRoomType").innerText = slots.room_type.toUpperCase();
  if (slots.check_in) document.getElementById("slotCheckIn").innerText = slots.check_in;
  if (slots.check_out) document.getElementById("slotCheckOut").innerText = slots.check_out;
  if (slots.num_guests) document.getElementById("slotGuests").innerText = slots.num_guests;
  if (slots.total_price) document.getElementById("slotPrice").innerText = `₹${slots.total_price.toLocaleString()}`;
}

function showBookingConfirmation(code, totalPrice) {
  const badge = document.getElementById("bookingBadge");
  if (badge) {
    badge.className = "text-[10px] font-bold px-2 py-0.5 rounded bg-emerald-500/20 text-emerald-400 border border-emerald-500/40 uppercase tracking-wider";
    badge.innerText = "Confirmed";
  }

  const card = document.getElementById("confirmedCard");
  const codeEl = document.getElementById("confirmationCodeText");
  if (codeEl) codeEl.innerText = code;
  if (card) card.classList.remove("hidden");
}

async function fetchRooms() {
  try {
    const res = await fetch("/rooms");
    if (res.ok) {
      const rooms = await res.json();
      const list = document.getElementById("roomList");
      if (list) {
        list.innerHTML = "";
        rooms.forEach((r) => {
          const item = document.createElement("div");
          item.className = "p-2.5 rounded-lg bg-slate-800/50 border border-slate-700/50 flex justify-between items-center";
          item.innerHTML = `
            <div>
              <p class="font-semibold text-slate-200">${r.name}</p>
              <p class="text-[10px] text-slate-400">${r.amenities ? r.amenities.slice(0, 3).join(", ") : ""}</p>
            </div>
            <span class="font-bold text-amber-400">₹${Number(r.price_per_night).toLocaleString()}/nt</span>
          `;
          list.appendChild(item);
        });
      }
    }
  } catch (e) {
    console.error("Failed to fetch room catalog:", e);
  }
}

// Direct Text Form Submit Handler
async function handleSendText(event) {
  event.preventDefault();
  ensureAudioContextActive();

  const inputEl = document.getElementById("chatInput");
  const text = inputEl.value.trim();
  if (!text) return;

  inputEl.value = "";
  appendTranscript("guest", text, formatLanguageName(currentSessionLanguage));
  updateStatusText("⏳ Maya is thinking...");
  setVoiceActivityStatus("processing", "Processing your message...");

  try {
    const formData = new FormData();
    formData.append("text", text);

    const resp = await fetch("/voice/chat", {
      method: "POST",
      body: formData,
    });

    if (resp.ok) {
      const data = await resp.json();
      if (data.language) {
        currentSessionLanguage = data.language;
        updateLanguageBadge(data.language);
      }
      if (data.reply_text) {
        appendTranscript("agent", data.reply_text, formatLanguageName(data.language));
      }
      if (data.slots) {
        updateReservationCard(data.slots);
        if (data.slots.booking_confirmed && data.slots.confirmation_code) {
          showBookingConfirmation(data.slots.confirmation_code, data.slots.total_price);
        }
      }
      if (data.audio_base64) {
        updateStatusText("🔊 Maya is speaking...");
        setVoiceActivityStatus("agent_speaking", "Maya is speaking...");
        setAgentSpeaking(true);
        await playBase64Audio(data.audio_base64);
        setAgentSpeaking(false);
      }
      updateStatusText("Maya is ready.");
      setVoiceActivityStatus(isCallActive ? "listening" : "standby", isCallActive ? "Listening... Speak anytime in English, தமிழ், or Tanglish" : "Microphone: Standby");
    }
  } catch (err) {
    console.error("Send text error:", err);
    updateStatusText("Error: " + err.message);
    setVoiceActivityStatus("error", "Error: " + err.message);
  }
}

// ==============================================================================
// Twilio Telephony Outbound Call Trigger
// ==============================================================================

async function triggerTwilioPhoneCall() {
  const btn = document.getElementById("triggerTwilioCallBtn");
  const btnText = document.getElementById("triggerTwilioCallBtnText");
  if (btnText) btnText.innerText = "Dialing...";
  if (btn) btn.disabled = true;

  try {
    const res = await fetch("/twilio/call", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ to_phone: "+919994388773" }),
    });
    const data = await res.json();
    if (data.success) {
      appendTranscript("agent", `📞 Maya is placing an outbound call to your mobile (+91 9994388773) via Twilio (+1 515 758 7590). Please answer your phone!`);
      alert(`Calling your phone (+91 9994388773)!\n\nTwilio Call SID: ${data.call_sid}\nWhen you answer, Maya will greet you.`);
    } else if (data.setup_required) {
      alert(`Twilio Telephony Notice:\n\n${data.message}\n\n${data.instructions || ""}`);
    } else {
      alert(`Call dispatch notice:\n${data.message}`);
    }
  } catch (err) {
    alert("Error triggering Twilio call: " + (err.message || err));
  } finally {
    if (btnText) btnText.innerText = "Call My Phone";
    if (btn) btn.disabled = false;
  }
}

// Global user interaction listener to wake up AudioContext if suspended
document.addEventListener("click", () => {
  ensureAudioContextActive();
});
document.addEventListener("keydown", () => {
  ensureAudioContextActive();
});

// Initial Page Load
window.addEventListener("DOMContentLoaded", () => {
  fetchRooms();
  checkVoiceServiceStatus();
  autoDetectAndSelectDevice(false);
  setInterval(checkVoiceServiceStatus, 15000);
});
