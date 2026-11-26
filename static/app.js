/* VayuMitra AI — Real-Time Voice-First, Picture-First Urban Air Quality Companion */
(() => {
  'use strict';

  const $ = (id) => document.getElementById(id);

  // Core UI Elements
  const srAnnouncer = $('sr-announcer');
  const apiStatusBadge = $('api-status-badge');
  const micBtn = $('mic-btn');
  const orbWrapper = $('orb-wrapper');
  const soundwave = $('soundwave');
  const voiceStatus = $('voice-status');
  const voiceSubtext = $('voice-subtext');
  const voiceIndicatorPill = $('voice-indicator-pill');
  const handsfreeBtn = $('handsfree-btn');
  const stopTtsBtn = $('stop-tts-btn');
  const replayTtsBtn = $('replay-tts-btn');
  const whatsappBtn = $('whatsapp-btn');
  const heroPhotoBtn = $('hero-photo-btn');
  const emergencyBtn = $('emergency-btn');
  const cameraBtn = $('camera-btn');
  const photoInput = $('photo-input');
  const chatMessages = $('chat-messages');
  const chatForm = $('chat-form');
  const chatInput = $('chat-input');
  const sendButton = $('send-button');
  const cityInput = $('city-input');
  const gpsStatusLabel = $('gps-status-label');
  const refreshGpsBtn = $('refresh-gps-btn');
  const locationControlGroup = $('location-control-group');
  const langSelect = $('lang-select');
  const modeSelect = $('mode-select');
  const pendingPhotoBar = $('pending-photo-bar');
  const pendingPhotoThumb = $('pending-photo-thumb');
  const pendingPhotoInfo = $('pending-photo-info');
  const removePhotoBtn = $('remove-photo-btn');
  const askProfileBtn = $('ask-profile-btn');
  const newChatBtn = $('new-chat-btn');

  // Meter, Clock & Hourly Chart Elements
  const meterCard = $('meter-card');
  const meterTitle = $('meter-title');
  const meterSubtitle = $('meter-subtitle');
  const meterSpeakBtn = $('meter-speak-btn');
  const cigIcons = $('cig-icons');
  const cigExplain = $('cig-explain');
  const exactLocationMeta = $('exact-location-meta');
  const lightRed = $('light-red');
  const lightOrange = $('light-orange');
  const lightGreen = $('light-green');
  const clockTitle = $('clock-title');
  const clockSubtitle = $('clock-subtitle');
  const clockSpeakBtn = $('clock-speak-btn');
  const hourlyStripWrap = $('hourly-strip-wrap');
  const hourlyBars = $('hourly-bars');
  const hourlyBestBadge = $('hourly-best-badge');

  // 4 Tap-to-Hear Picture Tiles
  const tileMask = $('tile-mask');
  const tileWindow = $('tile-window');
  const tileFamily = $('tile-family');
  const tileHome = $('tile-home');

  // Routine Planner Elements
  const routineForm = $('routine-form');
  const buildPlanBtn = $('build-plan-btn');
  const routineResults = $('routine-results');
  const speakPlanBtn = $('speak-plan-btn');
  const sharePlanBtn = $('share-plan-btn');
  const commuteKmEl = $('commute-km');
  const outdoorHoursEl = $('outdoor-hours');
  const habitExhaustEl = $('habit-exhaust');
  const habitWasteEl = $('habit-waste');

  // App State
  let previousInteractionId = null;
  let liveCoordinates = null;
  let liveAqiValue = null;
  let livePm25Value = null;
  let livePm10Value = null;
  let liveWeatherSummary = '';
  let liveExactAddress = '';
  let liveGpsAccuracyM = null;
  let liveEnvProvider = '';
  let aqiIsLive = false;
  let liveHourlyAqi = [];
  let currentCityLabel = 'Locating...';
  let lastResolvedCityValue = '';
  let serverHasEnvKey = false;
  let pendingPhoto = null;
  let selectedProfile = 'Sabhi Parivar (Whole Family)';
  let handsFreeMode = false;
  let lastDisplayReply = 'Namaste! Main VayuMitra hoon.';
  let lastSpokenReply = 'नमस्ते! मैं वायुमित्र हूँ।';
  let lastMeterSpoken = '';
  let lastClockSpoken = '';
  let lastRoutinePlan = null;
  let tileSpoken = { mask: '', window: '', family: '', home: '' };
  let isListening = false;
  let recognition = null;
  let activeSyncTimer = null;
  let activeSpeechToken = 0;
  let liveUserBubble = null;

  function getDict(lang = langSelect.value) {
    return (window.VAYU_I18N && window.VAYU_I18N[lang]) || window.VAYU_I18N.Hinglish;
  }

  function announcePolite(message) {
    if (!srAnnouncer || !message) return;
    srAnnouncer.textContent = '';
    setTimeout(() => { srAnnouncer.textContent = message; }, 80);
  }

  // ---------------------------------------------------------------------------
  // 0. Accessible After-Interaction Validation Sync
  // ---------------------------------------------------------------------------
  function initAccessibleValidation(form) {
    if (!form) return;
    const linkError = (el, shown) => {
      const errorId = el.dataset.error;
      if (!errorId) return;
      const ids = (el.getAttribute('aria-describedby') || '')
        .split(/\s+/)
        .filter((id) => id && id !== errorId);
      if (shown) ids.push(errorId);
      if (ids.length) el.setAttribute('aria-describedby', ids.join(' '));
      else el.removeAttribute('aria-describedby');
    };

    const syncField = (el) => {
      if (!el.matches?.('input, select, textarea')) return;
      const supportsUserInvalid = CSS.supports('selector(:user-invalid)');
      const invalid = supportsUserInvalid ? el.matches(':user-invalid') : !el.validity.valid;
      el.classList.toggle('user-invalid-fallback', !supportsUserInvalid && invalid);
      el.setAttribute('aria-invalid', invalid ? 'true' : 'false');
      linkError(el, invalid);
    };

    form.querySelectorAll('input, select, textarea').forEach((el) => el.setAttribute('aria-invalid', 'false'));
    form.addEventListener('blur', (e) => syncField(e.target), true);
    form.addEventListener('input', (e) => {
      if (e.target.getAttribute('aria-invalid') === 'true') syncField(e.target);
    });
    form.addEventListener('invalid', (e) => syncField(e.target), true);
  }

  // ---------------------------------------------------------------------------
  // 1. Server Health Badge
  // ---------------------------------------------------------------------------
  function renderApiBadge() {
    const dict = getDict();
    if (serverHasEnvKey) {
      apiStatusBadge.className = 'api-status-badge live';
      apiStatusBadge.textContent = dict.liveBadge;
    } else {
      apiStatusBadge.className = 'api-status-badge demo';
      apiStatusBadge.textContent = dict.demoBadge;
    }
  }

  async function checkServerHealth() {
    try {
      const res = await fetch('/api/health');
      if (res.ok) {
        const info = await res.json();
        serverHasEnvKey = Boolean(info.has_env_api_key);
      }
    } catch (_) {
      serverHasEnvKey = false;
    }
    renderApiBadge();
  }

  // ---------------------------------------------------------------------------
  // 2. Complete Localization (Hinglish / Hindi / Marathi / Simple English)
  // ---------------------------------------------------------------------------
  function applyLanguageToUI(lang) {
    const dict = getDict(lang);
    document.documentElement.lang = dict.htmlLang || 'en';
    renderApiBadge();

    const setText = (id, value) => {
      const el = $(id);
      if (el && value !== undefined) el.textContent = value;
    };

    setText('brand-title', dict.brandTitle);
    setText('brand-subtitle', dict.brandSubtitle);
    setText('lang-label', dict.langLabel);
    setText('mode-label', dict.modeLabel);
    setText('opt-mode-concise', dict.modeConcise);
    setText('opt-mode-detailed', dict.modeDetailed);
    setText('nav-routine-btn', dict.navRoutineBtn);
    setText('meter-speak-btn', dict.bigListenBtn);
    setText('emergency-btn', dict.emergencyBtn);
    setText('clock-speak-btn', dict.clockSpeakBtn);
    setText('hourly-heading', dict.hourlyHeading);

    setText('pic-guide-title', dict.picGuideTitle);
    setText('tile-mask-title', dict.picMaskTitle);
    setText('tile-window-title', dict.picWindowTitle);
    setText('tile-family-title', dict.picFamilyTitle);
    setText('tile-home-title', dict.picHomeTitle);
    setText('tile-home-badge', dict.picHomeBadge);
    setText('tile-home-sub', dict.picHomeSub);
    tileSpoken.home = dict.picHomeSpoken;

    if (!isListening && !orbWrapper.classList.contains('speaking')) {
      setText('voice-status', dict.voiceIdle);
      setText('voice-subtext', dict.voiceSubIdle);
    }
    handsfreeBtn.textContent = handsFreeMode ? dict.handsfreeOn : dict.handsfreeOff;
    setText('stop-tts-btn', dict.stopTtsBtn);
    setText('replay-tts-btn', dict.replayTtsBtn);
    setText('hero-photo-btn', dict.heroPhotoBtn);
    setText('whatsapp-btn', dict.whatsappBtn);

    setText('profile-label', dict.profileLabel);
    setText('prof-all', dict.profAll);
    setText('prof-elderly', dict.profElderly);
    setText('prof-kids', dict.profKids);
    setText('prof-worker', dict.profWorker);
    setText('prof-pregnant', dict.profPregnant);
    setText('ask-profile-btn', dict.askProfileBtn);

    setText('chat-heading', dict.chatTitle);
    setText('new-chat-btn', dict.newChatBtn);
    setText('initial-welcome-msg', dict.welcomeMsg);
    setText('chip-1', dict.chip1Text);
    $('chip-1')?.setAttribute('data-prompt', dict.chip1Prompt);
    setText('chip-2', dict.chip2Text);
    $('chip-2')?.setAttribute('data-prompt', dict.chip2Prompt);
    setText('chip-3', dict.chip3Text);
    $('chip-3')?.setAttribute('data-prompt', dict.chip3Prompt);
    setText('camera-btn', dict.cameraBtn);
    if (chatInput) chatInput.placeholder = dict.chatPlaceholder;
    setText('send-button', dict.sendBtn);

    setText('pillars-heading', dict.pillarsHeading);
    setText('p1-title', dict.p1Title);
    setText('p1-desc', dict.p1Desc);
    $('pillar-1')?.setAttribute('data-prompt', dict.p1Prompt);
    setText('p2-title', dict.p2Title);
    setText('p2-desc', dict.p2Desc);
    $('pillar-2')?.setAttribute('data-prompt', dict.p2Prompt);
    setText('p3-title', dict.p3Title);
    setText('p3-desc', dict.p3Desc);
    $('pillar-3')?.setAttribute('data-prompt', dict.p3Prompt);
    setText('p4-title', dict.p4Title);
    setText('p4-desc', dict.p4Desc);
    $('pillar-4')?.setAttribute('data-prompt', dict.p4Prompt);

    // Picture-tap Routine Planner labels (100% localized!)
    setText('routine-heading', dict.routineHeading);
    setText('routine-sub', dict.routineSub);
    setText('preset-label', dict.presetLabel);
    setText('preset-office', dict.presetOffice);
    setText('preset-senior', dict.presetSenior);
    setText('preset-worker', dict.presetWorker);
    setText('leg-commute', dict.legCommute);
    setText('lbl-opt-walk', dict.optWalk);
    setText('lbl-opt-scooter', dict.optScooter);
    setText('lbl-opt-auto', dict.optAuto);
    setText('lbl-opt-car', dict.optCar);
    setText('lbl-opt-bus', dict.optBus);
    setText('lbl-km-custom', dict.lblKmCustom);
    setText('leg-cooking', dict.legCooking);
    setText('lbl-opt-lpg', dict.optLpg);
    setText('lbl-opt-induction', dict.optInduction);
    setText('lbl-opt-wood', dict.optWood);
    setText('lbl-outdoor-hrs', dict.lblOutdoorHrs);
    setText('leg-members', dict.legMembers);
    setText('lbl-mem-kids', dict.memKids);
    setText('lbl-mem-elderly', dict.memElderly);
    setText('lbl-mem-worker', dict.memWorker);
    setText('lbl-mem-pregnant', dict.memPregnant);
    setText('lbl-habit-exhaust', dict.habitExhaust);
    setText('lbl-habit-waste', dict.habitWaste);
    setText('build-plan-btn', dict.buildPlanBtn);
    setText('plan-ready-title', dict.planReadyTitle);
    setText('speak-plan-btn', dict.speakPlanBtn);
    setText('share-plan-btn', dict.sharePlanBtn);
    setText('kpi-co2-lbl', dict.kpiCo2);
    setText('kpi-exposure-lbl', dict.kpiExposure);
    setText('kpi-savings-lbl', dict.kpiSavings);
    setText('kpi-trees-lbl', dict.kpiTrees);
    setText('card-low-emission-title', dict.cardLowEmission);
    setText('card-indoor-hacks-title', dict.cardIndoorHacks);
    setText('card-impact-insights-title', dict.cardImpactInsights);
    setText('footer-note', dict.footerNote);
  }

  // ---------------------------------------------------------------------------
  // 3. Live Hourly Clean Window + 24h Visual Bar + 4 Picture Tiles
  // ---------------------------------------------------------------------------
  function formatHourLabel(hour24) {
    const h = ((hour24 % 24) + 24) % 24;
    const suffix = h >= 12 ? 'PM' : 'AM';
    const h12 = h % 12 === 0 ? 12 : h % 12;
    return `${h12} ${suffix}`;
  }

  function findBestCleanWindow() {
    if (!liveHourlyAqi.length) return null;
    const daytime = liveHourlyAqi.filter((item) => item.hour >= 7 && item.hour <= 20 && Number.isFinite(item.aqi));
    if (daytime.length < 2) return null;
    let best = null;
    for (let i = 0; i < daytime.length - 1; i++) {
      const avg = (daytime[i].aqi + daytime[i + 1].aqi) / 2;
      if (!best || avg < best.avg) {
        best = { startHour: daytime[i].hour, endHour: daytime[i + 1].hour + 1, avg: Math.round(avg) };
      }
    }
    return best;
  }

  function renderHourlyAqiBars() {
    if (!liveHourlyAqi.length) {
      hourlyStripWrap.hidden = true;
      return;
    }
    const nowHour = new Date().getHours();
    const sampled = liveHourlyAqi.filter((_, idx) => idx % 2 === 0).slice(0, 12);
    const maxAqi = Math.max(150, ...sampled.map((s) => (Number.isFinite(s.aqi) ? s.aqi : 0)));
    hourlyBars.innerHTML = '';

    sampled.forEach((slot) => {
      const aqi = Number.isFinite(slot.aqi) ? Math.round(slot.aqi) : 0;
      const col = document.createElement('div');
      col.className = 'hour-col';
      col.title = `${formatHourLabel(slot.hour)}: AQI ${aqi}`;

      const bar = document.createElement('div');
      const severity = aqi <= 75 ? 'clean' : aqi <= 125 ? 'moderate' : aqi <= 175 ? 'poor' : 'severe';
      bar.className = `hour-bar ${severity}${Math.abs(slot.hour - nowHour) <= 1 ? ' now-marker' : ''}`;
      bar.style.height = `${Math.max(18, Math.round((aqi / maxAqi) * 100))}%`;

      const lbl = document.createElement('span');
      lbl.className = 'hour-label';
      lbl.textContent = `${slot.hour}h`;

      col.appendChild(bar);
      col.appendChild(lbl);
      hourlyBars.appendChild(col);
    });

    const best = findBestCleanWindow();
    hourlyBestBadge.textContent = best
      ? `✨ ${formatHourLabel(best.startHour)}–${formatHourLabel(best.endHour)}`
      : '';
    hourlyStripWrap.hidden = false;
  }

  function updatePictureTiles(aqi, pm25) {
    const lang = langSelect.value;
    const bestWin = findBestCleanWindow();
    const winStr = bestWin ? `${formatHourLabel(bestWin.startHour)}–${formatHourLabel(bestWin.endHour)}` : '1 PM–3 PM';
    const setTile = (el, cls, badge, sub) => {
      el.className = `pic-tile ${cls}`;
      el.querySelector('.pic-badge').textContent = badge;
      el.querySelector('.pic-sub').textContent = sub;
    };

    if (aqi === null) return;

    if (aqi <= 90) {
      if (lang === 'English') {
        setTile(tileMask, 'status-safe', 'Optional 🟢', 'Air is clean—no mask needed outdoors');
        setTile(tileWindow, 'status-safe', 'Open OK 🟢', 'Open windows for fresh air right now');
        setTile(tileFamily, 'status-safe', 'Safe Outside 🟢', 'Kids & seniors can walk and play');
        tileSpoken.mask = 'The air is clean right now, so you do not need a mask outdoors.';
        tileSpoken.window = 'The air outside is fresh. You can safely keep your home windows open right now.';
        tileSpoken.family = 'Children and seniors can safely go outside for walks and playtime today.';
      } else if (lang === 'Marathi') {
        setTile(tileMask, 'status-safe', 'गरज नाही 🟢', 'हवा स्वच्छ आहे, मास्कशिवाय फिरू शकता');
        setTile(tileWindow, 'status-safe', 'उघडा 🟢', 'आता ताज्या हवेसाठी खिडक्या उघड्या ठेवा');
        setTile(tileFamily, 'status-safe', 'बाहेर सुरक्षित 🟢', 'मुले आणि ज्येष्ठ बाहेर फिरायला जाऊ शकतात');
        tileSpoken.mask = 'आत्ता बाहेरची हवा स्वच्छ आहे, त्यामुळे मास्कची गरज नाही.';
        tileSpoken.window = 'हवा चांगली आहे, तुम्ही आत्ता घराच्या खिडक्या उघड्या ठेवू शकता.';
        tileSpoken.family = 'आज मुले आणि ज्येष्ठ नागरिक आरामात बाहेर फिरू व खेळू शकतात.';
      } else if (lang === 'Hindi') {
        setTile(tileMask, 'status-safe', 'ज़रूरत नहीं 🟢', 'हवा साफ है, बिना मास्क बाहर जा सकते हैं');
        setTile(tileWindow, 'status-safe', 'खोल सकते हैं 🟢', 'अभी ताज़ी हवा के लिए खिड़की खोलें');
        setTile(tileFamily, 'status-safe', 'बाहर सुरक्षित 🟢', 'बच्चे और बुजुर्ग बाहर टहल सकते हैं');
        tileSpoken.mask = 'अभी बाहर की हवा साफ है, इसलिए मास्क की ज़रूरत नहीं है।';
        tileSpoken.window = 'बाहर की हवा अच्छी है, आप अभी घर की खिड़की खोलकर ताज़ी हवा आने दें।';
        tileSpoken.family = 'बच्चे और बुजुर्ग आज आराम से बाहर टहलने और खेलने जा सकते हैं।';
      } else {
        setTile(tileMask, 'status-safe', 'Zaroorat Nahi 🟢', 'Hawa saaf hai, bina mask ja sakte hain');
        setTile(tileWindow, 'status-safe', 'Khol Sakte Hain 🟢', 'Abhi taazi hawa ke liye khidki kholein');
        setTile(tileFamily, 'status-safe', 'Bahar Safe 🟢', 'Bacche aur buzurg bahar ja sakte hain');
        tileSpoken.mask = 'अभी बाहर की हवा साफ है, इसलिए मास्क की ज़रूरत नहीं है।';
        tileSpoken.window = 'बाहर की हवा अच्छी है, आप अभी घर की खिड़की खोल सकते हैं।';
        tileSpoken.family = 'बच्चे और बुजुर्ग आज आराम से बाहर जा सकते हैं।';
      }
      return;
    }

    const isSevere = aqi > 170;
    const statusCls = isSevere ? 'status-danger' : 'status-warn';
    if (lang === 'English') {
      setTile(tileMask, statusCls, isSevere ? 'Must Wear 🔴' : 'Wear Mask 🟠', 'Wear N95 mask or 3-layer cotton cloth outside');
      setTile(tileWindow, statusCls, 'Keep Closed 🔴', `Open only 15 min around ${winStr}`);
      setTile(tileFamily, statusCls, isSevere ? 'Stay Indoors 🔴' : 'Limit Outdoors 🟠', 'Skip morning/evening walks for kids & elders');
      tileSpoken.mask = 'Wear an N95 mask or tie a clean 3-layer cotton cloth tightly over your nose and mouth before stepping outside.';
      tileSpoken.window = `Keep windows closed right now. Open them briefly for 15 minutes only during today's cleanest window around ${winStr}.`;
      tileSpoken.family = 'Keep children and senior citizens indoors during morning and evening smog to protect their lungs.';
    } else if (lang === 'Marathi') {
      setTile(tileMask, statusCls, isSevere ? 'नक्की बांधा 🔴' : 'मास्क वापरा 🟠', 'बाहेर जाताना N95 मास्क किंवा स्वच्छ सुती रुमाल बांधा');
      setTile(tileWindow, statusCls, 'बंद ठेवा 🔴', `फक्त ${winStr} दरम्यान 15 मिनिटे उघडा`);
      setTile(tileFamily, statusCls, isSevere ? 'घरात थांबा 🔴' : 'काळजी घ्या 🟠', 'सकाळ-संध्याकाळ मुले व ज्येष्ठांनी बाहेर जाऊ नये');
      tileSpoken.mask = 'बाहेर जाताना नाक आणि तोंडावर एन पंच्याण्णव मास्क किंवा स्वच्छ तीन पदरी सुती रुमाल घट्ट बांधा.';
      tileSpoken.window = `आत्ता घराच्या खिडक्या बंद ठेवा. आज फक्त ${winStr} दरम्यान पंधरा मिनिटे खिडकी उघडा.`;
      tileSpoken.family = 'सकाळ आणि संध्याकाळच्या धुरात लहान मुले आणि ज्येष्ठ नागरिकांनी घरातच थांबावे.';
    } else if (lang === 'Hindi') {
      setTile(tileMask, statusCls, isSevere ? 'बहुत ज़रूरी 🔴' : 'मास्क पहनें 🟠', 'बाहर N95 मास्क या 3 परत सूती गमछा बाँधें');
      setTile(tileWindow, statusCls, 'बंद रखें 🔴', `सिर्फ़ ${winStr} के बीच 15 मिनट खोलें`);
      setTile(tileFamily, statusCls, isSevere ? 'अंदर रहें 🔴' : 'सावधानी रखें 🟠', 'सुबह-शाम बच्चे व बुजुर्ग बाहर न जाएँ');
      tileSpoken.mask = 'बाहर निकलते समय नाक और मुँह पर एन पचानवे मास्क या साफ तीन परत वाला सूती गमछा कसकर बाँधें।';
      tileSpoken.window = `अभी घर की खिड़की बंद रखें। आज सिर्फ ${winStr} के बीच पंद्रह मिनट खिड़की खोलें।`;
      tileSpoken.family = 'सुबह और शाम के धुएँ में बच्चों और बुजुर्गों को घर के अंदर ही रखें।';
    } else {
      setTile(tileMask, statusCls, isSevere ? 'Bahut Zaroori 🔴' : 'Mask Pehnein 🟠', 'Bahar N95 mask ya 3-layer suti gamchha bandhein');
      setTile(tileWindow, statusCls, 'Band Rakhein 🔴', `Sirf ${winStr} mein 15 min kholein`);
      setTile(tileFamily, statusCls, isSevere ? 'Andar Rahein 🔴' : 'Savdhan Rahein 🟠', 'Subah-shaam bacche aur buzurg bahar na jayein');
      tileSpoken.mask = 'बाहर निकलते समय नाक और मुँह पर एन पचानवे मास्क या साफ तीन परत वाला सूती गमछा कसकर बाँधें।';
      tileSpoken.window = `अभी घर की खिड़की बंद रखें। आज सिर्फ ${winStr} के बीच पंद्रह मिनट खिड़की खोलें।`;
      tileSpoken.family = 'सुबह और शाम के धुएँ में बच्चों और बुजुर्गों को घर के अंदर ही रखें।';
    }
  }

  function updateSafeWindowClock() {
    const now = new Date();
    const hour = now.getHours();
    const timeStr = now.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    const lang = langSelect.value;
    const bestWin = findBestCleanWindow();
    const bestWindowStr = bestWin
      ? `${formatHourLabel(bestWin.startHour)}–${formatHourLabel(bestWin.endHour)}`
      : '1 PM–3 PM';
    const effectiveAqi = liveAqiValue;

    if (effectiveAqi !== null && effectiveAqi <= 75) {
      if (lang === 'English') {
        clockTitle.textContent = `🟢 Clean Air Now (${timeStr}): Open Windows OK`;
        clockSubtitle.textContent = `Best fresh-air window today: ${bestWindowStr}.`;
        lastClockSpoken = `At ${timeStr}, the air outside is clean. You can safely keep windows open.`;
      } else if (lang === 'Marathi') {
        clockTitle.textContent = `🟢 आत्ता (${timeStr}) हवा स्वच्छ आहे: खिडक्या उघडा`;
        clockSubtitle.textContent = `आजची सर्वात स्वच्छ वेळ: ${bestWindowStr}.`;
        lastClockSpoken = `आत्ता ${timeStr} वाजता बाहेरची हवा स्वच्छ आहे. तुम्ही खिडक्या उघड्या ठेवू शकता.`;
      } else if (lang === 'Hindi') {
        clockTitle.textContent = `🟢 अभी (${timeStr}) हवा साफ है: खिड़की खोलें`;
        clockSubtitle.textContent = `आज सबसे साफ समय: ${bestWindowStr}।`;
        lastClockSpoken = `अभी ${timeStr} बजे बाहर की हवा साफ है। आप घर की खिड़की खोल सकते हैं।`;
      } else {
        clockTitle.textContent = `🟢 Abhi (${timeStr}) Hawa Saaf Hai: Khidki Khol Sakte Hain`;
        clockSubtitle.textContent = `Aaj ka sabse saaf samay: ${bestWindowStr}.`;
        lastClockSpoken = `अभी ${timeStr} बजे बाहर की हवा साफ है। आप घर की खिड़की खोल सकते हैं।`;
      }
      return;
    }

    const isBestNow = bestWin && hour >= bestWin.startHour && hour < bestWin.endHour;
    if (lang === 'English') {
      clockTitle.textContent = isBestNow
        ? `🟡 Best Window Now (${timeStr}): Brief 15-Min Ventilation OK`
        : `🔴 Keep Windows Closed Now (${timeStr})`;
      clockSubtitle.textContent = `Today's cleanest window for fresh air: ${bestWindowStr}.`;
      lastClockSpoken = isBestNow
        ? `At ${timeStr}, this is today's cleanest window. Open windows for 15 minutes only.`
        : `At ${timeStr}, smog is high. Keep windows closed and open them briefly around ${bestWindowStr}.`;
    } else if (lang === 'Marathi') {
      clockTitle.textContent = isBestNow
        ? `🟡 आत्ता (${timeStr}) चांगली वेळ: 15 मिनिटे खिडकी उघडा`
        : `🔴 आत्ता (${timeStr}) धूर जास्त आहे: खिडक्या बंद ठेवा`;
      clockSubtitle.textContent = `आजची सर्वात स्वच्छ वेळ: ${bestWindowStr}.`;
      lastClockSpoken = isBestNow
        ? `आत्ता ${timeStr} वाजता आजची सर्वात स्वच्छ वेळ आहे. पंधरा मिनिटे खिडकी उघडा.`
        : `आत्ता ${timeStr} वाजता बाहेर धूर जास्त आहे. खिडक्या बंद ठेवा आणि फक्त ${bestWindowStr} दरम्यान उघडा.`;
    } else if (lang === 'Hindi') {
      clockTitle.textContent = isBestNow
        ? `🟡 अभी (${timeStr}) सबसे साफ समय: 15 मिनट खिड़की खोलें`
        : `🔴 अभी (${timeStr}) धुआँ ज़्यादा है: खिड़की बंद रखें`;
      clockSubtitle.textContent = `आज खिड़की खोलने का सही समय: ${bestWindowStr}।`;
      lastClockSpoken = isBestNow
        ? `अभी ${timeStr} बजे आज का सबसे साफ समय है। पंद्रह मिनट के लिए खिड़की खोल सकते हैं।`
        : `अभी ${timeStr} बजे बाहर धुआँ ज़्यादा है। खिड़की बंद रखें और सिर्फ ${bestWindowStr} के बीच खोलें।`;
    } else {
      clockTitle.textContent = isBestNow
        ? `🟡 Abhi (${timeStr}) Sabse Saaf Samay: 15 Min Khidki Kholein`
        : `🔴 Abhi (${timeStr}) Dhuan Zyada Hai: Khidki Band Rakhein`;
      clockSubtitle.textContent = `Aaj khidki kholne ka sahi samay: ${bestWindowStr}.`;
      lastClockSpoken = isBestNow
        ? `अभी ${timeStr} बजे आज का सबसे साफ समय है। पंद्रह मिनट के लिए खिड़की खोल सकते हैं।`
        : `अभी ${timeStr} बजे बाहर धुआँ ज़्यादा है। खिड़की बंद रखें और सिर्फ ${bestWindowStr} के बीच खोलें।`;
    }
  }

  // ---------------------------------------------------------------------------
  // 4. Unified Server-Side Environment Proxy (Google Air Quality + Open-Meteo AQI & Weather)
  // ---------------------------------------------------------------------------
  function renderExactLocationMeta() {
    if (!exactLocationMeta) return;
    const parts = [];
    if (liveExactAddress) {
      const accStr = liveGpsAccuracyM !== null ? ` (±${Math.round(liveGpsAccuracyM)}m GPS)` : '';
      parts.push(`📍 ${liveExactAddress}${accStr}`);
    }
    if (liveWeatherSummary) {
      parts.push(liveWeatherSummary);
    }
    if (liveEnvProvider) {
      parts.push(`📡 ${liveEnvProvider}`);
    }
    exactLocationMeta.textContent = parts.join('  •  ') || '📍 Detecting exact street & live weather...';
  }

  async function fetchLiveAqiSensor(lat, lon, cityName) {
    currentCityLabel = cityName;
    try {
      const res = await fetch(`/api/environment?lat=${encodeURIComponent(lat)}&lon=${encodeURIComponent(lon)}`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      liveAqiValue = data.aqi !== undefined && data.aqi !== null ? Math.round(data.aqi) : 100;
      livePm25Value = data.pm25 !== undefined && data.pm25 !== null ? Math.round(data.pm25) : 35;
      livePm10Value = data.pm10 !== undefined && data.pm10 !== null ? Math.round(data.pm10) : null;
      aqiIsLive = Boolean(data.is_live);
      liveEnvProvider = data.provider || 'Open-Meteo';
      liveHourlyAqi = Array.isArray(data.hourly) ? data.hourly : [];

      const w = data.weather || {};
      const wParts = [];
      if (w.temp_c !== undefined && w.temp_c !== null) wParts.push(`🌡️ ${w.temp_c}°C`);
      if (w.humidity_pct !== undefined && w.humidity_pct !== null) wParts.push(`💧 ${w.humidity_pct}%`);
      if (w.wind_kmh !== undefined && w.wind_kmh !== null) wParts.push(`💨 ${w.wind_kmh} km/h`);
      liveWeatherSummary = wParts.join(' ');
    } catch (_) {
      liveAqiValue = 165;
      livePm25Value = 75;
      livePm10Value = null;
      liveHourlyAqi = [];
      liveWeatherSummary = '';
      liveEnvProvider = 'Offline Estimate';
      aqiIsLive = false;
    }
    renderTrafficLightMeter(cityName, liveAqiValue, livePm25Value);
    renderExactLocationMeta();
    updateSafeWindowClock();
    renderHourlyAqiBars();
    updatePictureTiles(liveAqiValue, livePm25Value);
  }

  function renderTrafficLightMeter(cityName, aqi, pm25) {
    if (aqi === null || pm25 === null) return;
    const lang = langSelect.value;
    const cigarettes = Math.max(1, Math.round(pm25 / 22));
    const shownIcons = aqi <= 75 ? '🌿✨' : '🚬'.repeat(Math.min(8, cigarettes));
    cigIcons.textContent = shownIcons;

    lightRed.classList.remove('active');
    lightOrange.classList.remove('active');
    lightGreen.classList.remove('active');

    if (aqi <= 90) {
      document.body.setAttribute('data-aqi-theme', 'good');
      lightGreen.classList.add('active');
      meterCard.style.borderColor = 'var(--accent-green)';
      if (lang === 'English') {
        meterTitle.textContent = `🟢 Good & Safe Air in ${cityName}`;
        meterSubtitle.textContent = `Air is clean (AQI ${aqi}). Children and seniors can safely go outside.`;
        cigExplain.textContent = `Fresh air today — very low smoke!`;
        lastMeterSpoken = `Good news! Air in ${cityName} is clean today. Children and senior citizens can safely go outside and keep windows open.`;
      } else if (lang === 'Marathi') {
        meterTitle.textContent = `🟢 ${cityName} मध्ये हवा स्वच्छ आहे`;
        meterSubtitle.textContent = `आज हवा श्वास घ्यायला सुरक्षित आहे (AQI ${aqi}). मुले व ज्येष्ठ बाहेर जाऊ शकतात.`;
        cigExplain.textContent = `आज हवेत धूर खूप कमी आहे—हवा स्वच्छ आहे!`;
        lastMeterSpoken = `आनंदाची बातमी! आज ${cityName} मध्ये हवा स्वच्छ आहे. मुले आणि ज्येष्ठ नागरिक आरामात बाहेर फिरू शकतात.`;
      } else if (lang === 'Hindi') {
        meterTitle.textContent = `🟢 ${cityName} में हवा साफ है`;
        meterSubtitle.textContent = `आज साँस लेने के लिए हवा ठीक है (AQI ${aqi})। बच्चे और बुजुर्ग बाहर जा सकते हैं।`;
        cigExplain.textContent = `आज हवा में धुआँ बहुत कम है—ताज़ी हवा है!`;
        lastMeterSpoken = `अच्छी खबर! आज ${cityName} में हवा साफ है और खतरे का सिग्नल हरा है। बच्चे और बुजुर्ग आराम से बाहर जा सकते हैं।`;
      } else {
        meterTitle.textContent = `🟢 ${cityName} Mein Hawa Saaf Hai`;
        meterSubtitle.textContent = `Aaj saans lene ke liye hawa theek hai (AQI ${aqi}). Bacche aur buzurg bahar ja sakte hain.`;
        cigExplain.textContent = `Aaj hawa mein dhuan bahut kam hai—saaf hawa hai!`;
        lastMeterSpoken = `अच्छी खबर! आज ${cityName} में हवा साफ है और खतरे का सिग्नल हरा है। बच्चे और बुजुर्ग आराम से बाहर जा सकते हैं।`;
      }
    } else if (aqi <= 170) {
      document.body.setAttribute('data-aqi-theme', 'caution');
      lightOrange.classList.add('active');
      meterCard.style.borderColor = 'var(--accent-orange)';
      if (lang === 'English') {
        meterTitle.textContent = `🟠 Caution: Smoky Air in ${cityName}`;
        meterSubtitle.textContent = `Wear an N95 mask or clean cotton cloth outdoors (AQI ${aqi}).`;
        cigExplain.textContent = `Like breathing ~${cigarettes} cigarettes of smoke without smoking!`;
        lastMeterSpoken = `Caution! Air in ${cityName} is smoky today, like breathing ${cigarettes} cigarettes without smoking. Wear a mask or cotton cloth outside, and use a wet mop at home.`;
      } else if (lang === 'Marathi') {
        meterTitle.textContent = `🟠 सावधान: ${cityName} मध्ये हवेत धूर आहे`;
        meterSubtitle.textContent = `बाहेर जाताना मास्क किंवा स्वच्छ सुती रुमाल बांधा (AQI ${aqi}).`;
        cigExplain.textContent = `न पिता रोज ~${cigarettes} सिगारेटचा धूर श्वासात जाण्यासारखे!`;
        lastMeterSpoken = `सावधान! आज ${cityName} च्या हवेत धूर आहे, अगदी न पिता ${cigarettes} सिगारेटचा धूर श्वासात जाण्यासारखे. बाहेर जाताना मास्क किंवा सुती रुमाल बांधा आणि घरात ओला पोछा मारा.`;
      } else if (lang === 'Hindi') {
        meterTitle.textContent = `🟠 सावधान: ${cityName} की हवा में धुआँ है`;
        meterSubtitle.textContent = `बाहर जाते समय मास्क या सूती कपड़ा बाँधें (AQI ${aqi})।`;
        cigExplain.textContent = `बिना पिए ~${cigarettes} सिगरेट के धुएँ जैसा नुकसान!`;
        lastMeterSpoken = `सावधान! आज ${cityName} की हवा में धुआँ है, बिल्कुल वैसे जैसे बिना पिए ${cigarettes} सिगरेट का धुआँ साँस में जा रहा हो। बाहर मास्क या सूती गमछा बाँधें और घर में गीला पोछा लगाएँ।`;
      } else {
        meterTitle.textContent = `🟠 Savdhan: ${cityName} Ki Hawa Mein Dhuan Hai`;
        meterSubtitle.textContent = `Bahar jaate waqt N95 mask ya saaf suti kapda bandhein (AQI ${aqi}).`;
        cigExplain.textContent = `Bina piye ~${cigarettes} cigarette ke dhuein jaisa nuksan!`;
        lastMeterSpoken = `सावधान! आज ${cityName} की हवा में धुआँ है, बिल्कुल वैसे जैसे बिना पिए ${cigarettes} सिगरेट का धुआँ साँस में जा रहा हो। बाहर मास्क या सूती गमछा बाँधें और घर में गीला पोछा लगाएँ।`;
      }
    } else {
      document.body.setAttribute('data-aqi-theme', 'danger');
      lightRed.classList.add('active');
      meterCard.style.borderColor = 'var(--accent-red)';
      if (lang === 'English') {
        meterTitle.textContent = `🔴 Red Alert: Toxic Smog in ${cityName}`;
        meterSubtitle.textContent = `Keep kids & seniors indoors; wear a tight mask outside (AQI ${aqi}).`;
        cigExplain.textContent = `Heavy smog — like breathing ~${cigarettes} cigarettes today!`;
        lastMeterSpoken = `Red alert! Air in ${cityName} has toxic smog today, like breathing ${cigarettes} cigarettes without smoking. Keep children and seniors indoors, close windows, and wear a tight mask outside.`;
      } else if (lang === 'Marathi') {
        meterTitle.textContent = `🔴 धोका: ${cityName} मध्ये विषारी धूर आहे!`;
        meterSubtitle.textContent = `मुले व ज्येष्ठांनी घरात राहावे, बाहेर मास्क नक्की बांधा (AQI ${aqi}).`;
        cigExplain.textContent = `अतिशय धूर — न पिता ~${cigarettes} सिगारेटचा धूर श्वासात जाण्यासारखे!`;
        lastMeterSpoken = `धोक्याचा इशारा! आज ${cityName} च्या हवेत खूप विषारी धूर आहे, अगदी न पिता ${cigarettes} सिगारेट ओढल्यासारखे. मुले आणि ज्येष्ठांनी घरातच थांबावे, खिडक्या बंद ठेवाव्यात आणि बाहेर मास्क बांधावा.`;
      } else if (lang === 'Hindi') {
        meterTitle.textContent = `🔴 खतरा: ${cityName} में ज़हरीला धुआँ है!`;
        meterSubtitle.textContent = `बच्चे-बुजुर्ग अंदर रहें, बाहर मास्क या 3 परत गमछा बाँधें (AQI ${aqi})।`;
        cigExplain.textContent = `बहुत ज़्यादा धुआँ — बिना पिए ~${cigarettes} सिगरेट बराबर!`;
        lastMeterSpoken = `लाल सिग्नल खतरा! आज ${cityName} की हवा में बहुत ज़हरीला धुआँ है, बिल्कुल वैसे जैसे बिना पिए ${cigarettes} सिगरेट का धुआँ साँस में जा रहा हो। बच्चों और बुजुर्गों को अंदर रखें और बाहर मास्क या गमछा कसकर बाँधें।`;
      } else {
        meterTitle.textContent = `🔴 Khatra: ${cityName} Mein Zehreela Dhuan Hai!`;
        meterSubtitle.textContent = `Bacche-buzurg andar rahein, bahar mask ya 3-layer gamchha bandhein (AQI ${aqi}).`;
        cigExplain.textContent = `Bahut zyada dhuan — bina piye ~${cigarettes} cigarette barabar!`;
        lastMeterSpoken = `लाल सिग्नल खतरा! आज ${cityName} की हवा में बहुत ज़हरीला धुआँ है, बिल्कुल वैसे जैसे बिना पिए ${cigarettes} सिगरेट का धुआँ साँस में जा रहा हो। बच्चों और बुजुर्गों को अंदर रखें और बाहर मास्क या गमछा कसकर बाँधें।`;
      }
    }
  }

  // ---------------------------------------------------------------------------
  // 5. High-Precision GPS Lock (watchPosition) + Reverse/Forward Geocoding
  // ---------------------------------------------------------------------------
  async function resolveExactAddressFromCoords(lat, lon, statusLabelText, accuracyMeters = null) {
    liveCoordinates = `${lat.toFixed(5)}, ${lon.toFixed(5)}`;
    liveGpsAccuracyM = Number.isFinite(accuracyMeters) ? accuracyMeters : null;
    gpsStatusLabel.textContent = statusLabelText;

    let displayCity = `GPS (${lat.toFixed(4)}, ${lon.toFixed(4)})`;
    let exactAddress = displayCity;
    let provider = 'GPS';

    try {
      const geoRes = await fetch(`/api/reverse-geocode?lat=${encodeURIComponent(lat)}&lon=${encodeURIComponent(lon)}`);
      if (geoRes.ok) {
        const geoData = await geoRes.json();
        if (geoData && geoData.display_name) {
          displayCity = geoData.display_name;
          exactAddress = geoData.exact_address || displayCity;
          provider = geoData.provider || 'Geocoder';
        }
      }
    } catch (_) { }

    cityInput.value = displayCity;
    lastResolvedCityValue = displayCity;
    liveExactAddress = exactAddress;
    const tooltipText = `${exactAddress} (${liveCoordinates}) • via ${provider}`;
    cityInput.title = tooltipText;
    if (locationControlGroup) locationControlGroup.title = tooltipText;
    renderExactLocationMeta();
    previousInteractionId = null;
    await fetchLiveAqiSensor(lat, lon, displayCity);
  }

  function acquireBestGpsFix(maxWaitMs = 5000, targetAccuracyM = 35) {
    return new Promise((resolve, reject) => {
      if (!('geolocation' in navigator)) {
        reject(new Error('unsupported'));
        return;
      }
      let bestPos = null;
      let finished = false;
      let watchId = null;

      const finish = (err) => {
        if (finished) return;
        finished = true;
        if (watchId !== null) navigator.geolocation.clearWatch(watchId);
        clearTimeout(timer);
        if (bestPos) resolve(bestPos);
        else reject(err || new Error('timeout'));
      };

      const timer = setTimeout(() => finish(new Error('timeout')), maxWaitMs);

      watchId = navigator.geolocation.watchPosition(
        (pos) => {
          if (!bestPos || (pos.coords.accuracy || 99999) < (bestPos.coords.accuracy || 99999)) {
            bestPos = pos;
          }
          if (pos.coords.accuracy && pos.coords.accuracy <= targetAccuracyM) {
            finish(null);
          }
        },
        (err) => {
          if (err && err.code === 1) finish(err); // Permission denied
          else if (!bestPos) finish(err);
        },
        { enableHighAccuracy: true, timeout: maxWaitMs, maximumAge: 0 }
      );
    });
  }

  async function detectLiveLocation() {
    gpsStatusLabel.textContent = '📡 GPS...';
    cityInput.value = 'Locating...';

    const fallbackToIP = async () => {
      const ipProviders = [
        async () => {
          const res = await fetch('https://ipwho.is/');
          const data = await res.json();
          if (data && data.success !== false && data.latitude && data.longitude) {
            return { lat: Number(data.latitude), lon: Number(data.longitude) };
          }
          return null;
        },
        async () => {
          const res = await fetch('https://ipapi.co/json/');
          const data = await res.json();
          if (data && data.latitude && data.longitude) {
            return { lat: Number(data.latitude), lon: Number(data.longitude) };
          }
          return null;
        }
      ];

      for (const fetchIp of ipProviders) {
        try {
          const ipLoc = await fetchIp();
          if (ipLoc) {
            await resolveExactAddressFromCoords(ipLoc.lat, ipLoc.lon, '📍 Area:', null);
            return;
          }
        } catch (_) { }
      }

      cityInput.value = 'Delhi NCR';
      lastResolvedCityValue = 'Delhi NCR';
      liveExactAddress = 'Delhi NCR';
      liveGpsAccuracyM = null;
      gpsStatusLabel.textContent = '📍 Area:';
      await fetchLiveAqiSensor(28.6139, 77.2090, 'Delhi NCR');
    };

    try {
      const position = await acquireBestGpsFix(5500, 35);
      await resolveExactAddressFromCoords(
        position.coords.latitude,
        position.coords.longitude,
        '🟢 GPS:',
        position.coords.accuracy
      );
    } catch (_) {
      await fallbackToIP();
    }
  }

  async function searchTypedLocation() {
    const query = cityInput.value.trim();
    if (!query || query === 'Locating...' || query === lastResolvedCityValue) return;
    gpsStatusLabel.textContent = '🔍 ...';
    try {
      const res = await fetch(`/api/geocode?q=${encodeURIComponent(query)}`);
      if (res.ok) {
        const geoData = await res.json();
        liveCoordinates = `${Number(geoData.lat).toFixed(5)}, ${Number(geoData.lon).toFixed(5)}`;
        cityInput.value = geoData.display_name || query;
        lastResolvedCityValue = cityInput.value;
        liveExactAddress = geoData.exact_address || cityInput.value;
        liveGpsAccuracyM = null;
        gpsStatusLabel.textContent = '📍 Area:';
        renderExactLocationMeta();
        previousInteractionId = null;
        await fetchLiveAqiSensor(Number(geoData.lat), Number(geoData.lon), cityInput.value);
        return;
      }
    } catch (_) { }
    gpsStatusLabel.textContent = '📍 Area:';
    lastResolvedCityValue = query;
  }

  // ---------------------------------------------------------------------------
  // 6. Zero-Typing Picture-Tap Family Daily Routine Planner
  // ---------------------------------------------------------------------------
  const ROUTINE_PRESETS = {
    office: {
      commute_mode: 'petrol_car',
      commute_km_per_day: 24,
      cooking_fuel: 'lpg',
      outdoor_hours_peak: 2,
      members: ['kids', 'elderly'],
      has_exhaust: true,
      burns_waste: false
    },
    senior: {
      commute_mode: 'auto_cab',
      commute_km_per_day: 6,
      cooking_fuel: 'lpg',
      outdoor_hours_peak: 1.5,
      members: ['elderly'],
      has_exhaust: false,
      burns_waste: true
    },
    worker: {
      commute_mode: 'petrol_scooter',
      commute_km_per_day: 35,
      cooking_fuel: 'biomass_wood',
      outdoor_hours_peak: 7,
      members: ['outdoor_worker', 'kids'],
      has_exhaust: false,
      burns_waste: true
    }
  };

  function applyRoutinePreset(presetKey) {
    const p = ROUTINE_PRESETS[presetKey];
    if (!p) return;
    const cmRadio = routineForm.querySelector(`input[name="commute_mode"][value="${p.commute_mode}"]`);
    if (cmRadio) cmRadio.checked = true;
    const ckRadio = routineForm.querySelector(`input[name="cooking_fuel"][value="${p.cooking_fuel}"]`);
    if (ckRadio) ckRadio.checked = true;
    commuteKmEl.value = String(p.commute_km_per_day);
    outdoorHoursEl.value = String(p.outdoor_hours_peak);
    habitExhaustEl.checked = Boolean(p.has_exhaust);
    habitWasteEl.checked = Boolean(p.burns_waste);
    routineForm.querySelectorAll('input[name="household_members"]').forEach((cb) => {
      cb.checked = p.members.includes(cb.value);
    });
    routineForm.requestSubmit();
  }

  function renderBulletList(listEl, items) {
    listEl.innerHTML = '';
    (items || []).forEach((item) => {
      const li = document.createElement('li');
      li.textContent = item;
      listEl.appendChild(li);
    });
  }

  function renderRoutinePlan(data) {
    lastRoutinePlan = data;
    const m = data.metrics || {};
    $('kpi-co2-val').textContent = `${m.weekly_co2_saved_kg ?? 0} kg`;
    $('kpi-exposure-val').textContent = `-${m.exposure_reduction_pct ?? 40}%`;
    $('kpi-savings-val').textContent = m.monthly_fuel_savings_inr > 0
      ? `₹${Number(m.monthly_fuel_savings_inr).toLocaleString('en-IN')}`
      : 'Clean Mode';
    $('kpi-trees-val').textContent = `~${m.annual_trees_equivalent ?? 1} 🌳`;

    renderBulletList($('list-low-emission'), data.low_emission_steps);
    renderBulletList($('list-indoor-hacks'), data.indoor_air_hacks);
    renderBulletList($('list-impact-insights'), data.impact_insights);

    const dict = getDict();
    $('plan-ready-title').textContent = `${dict.planReadyTitle} (${data.city})${data.ai_enhanced ? ' • ✨ Gemini AI' : ''}`;
    routineResults.hidden = false;
    announcePolite(`Family plan ready for ${data.city}.`);
  }

  async function handleRoutineSubmit(event) {
    event.preventDefault();
    if (!routineForm.checkValidity()) {
      routineForm.reportValidity();
      return;
    }
    const dict = getDict();
    buildPlanBtn.disabled = true;
    buildPlanBtn.textContent = dict.buildingPlanBtn;

    const commuteChecked = routineForm.querySelector('input[name="commute_mode"]:checked');
    const cookingChecked = routineForm.querySelector('input[name="cooking_fuel"]:checked');
    const selectedMembers = Array.from(
      routineForm.querySelectorAll('input[name="household_members"]:checked')
    ).map((el) => el.value);

    const bestWin = findBestCleanWindow();
    const cleanWindow = bestWin
      ? `${formatHourLabel(bestWin.startHour)}–${formatHourLabel(bestWin.endHour)}`
      : '1 PM–3 PM';

    const activeCity = (cityInput.value && cityInput.value !== 'Locating...') ? cityInput.value.trim() : 'Delhi NCR';
    const payload = {
      city: activeCity,
      live_aqi: liveAqiValue,
      live_pm25: livePm25Value,
      language: langSelect.value,
      routine: {
        commute_mode: commuteChecked ? commuteChecked.value : 'petrol_scooter',
        commute_km_per_day: Number(commuteKmEl.value),
        cooking_fuel: cookingChecked ? cookingChecked.value : 'lpg',
        outdoor_hours_peak: Number(outdoorHoursEl.value),
        household_members: selectedMembers.length ? selectedMembers : ['adults'],
        has_chimney_exhaust: habitExhaustEl.checked,
        burns_waste_or_incense: habitWasteEl.checked,
        clean_window: cleanWindow
      }
    };

    try {
      const res = await fetch('/api/routine-plan', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      if (res.ok) {
        const data = await res.json();
        renderRoutinePlan(data);
        routineResults.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
        if (data.spoken_summary) {
          speakAndStreamTogether(data.spoken_summary, data.spoken_summary, null);
        }
      }
    } catch (_) {
      announcePolite('Could not reach the server to build your plan.');
    } finally {
      buildPlanBtn.disabled = false;
      buildPlanBtn.textContent = dict.buildPlanBtn;
    }
  }

  // ---------------------------------------------------------------------------
  // 7. Natural Voice Selection (Hindi / Marathi / Indian English) + Synced TTS
  // ---------------------------------------------------------------------------
  function pickNaturalVoice(langMode) {
    const voices = window.speechSynthesis ? window.speechSynthesis.getVoices() : [];
    if (!voices.length) return null;

    if (langMode === 'English') {
      return (
        voices.find((v) => /neerja|prabhat|india/i.test(v.name) && /natural|online/i.test(v.name)) ||
        voices.find((v) => v.lang.toLowerCase() === 'en-in' && /google|microsoft/i.test(v.name)) ||
        voices.find((v) => v.lang.toLowerCase() === 'en-in') ||
        voices.find((v) => v.lang.toLowerCase().startsWith('en'))
      );
    }
    if (langMode === 'Marathi') {
      return (
        voices.find((v) => /aarohi|manohar|marathi/i.test(v.name) && /natural|online/i.test(v.name)) ||
        voices.find((v) => v.lang.toLowerCase() === 'mr-in') ||
        voices.find((v) => v.lang.toLowerCase().includes('mr')) ||
        voices.find((v) => v.lang.toLowerCase() === 'hi-in')
      );
    }
    return (
      voices.find((v) => /swara|madhur/i.test(v.name) && /natural|online/i.test(v.name)) ||
      voices.find((v) => v.lang.toLowerCase() === 'hi-in' && /google|natural|microsoft/i.test(v.name)) ||
      voices.find((v) => v.lang.toLowerCase() === 'hi-in') ||
      voices.find((v) => v.lang.toLowerCase().includes('hi'))
    );
  }

  function stopSpeakingAndSync() {
    activeSpeechToken++;
    if ('speechSynthesis' in window) window.speechSynthesis.cancel();
    if (activeSyncTimer) {
      clearInterval(activeSyncTimer);
      activeSyncTimer = null;
    }
    orbWrapper.classList.remove('speaking');
    soundwave.classList.remove('active');
    document.querySelectorAll('.msg.assistant.speaking-now').forEach((el) => el.classList.remove('speaking-now'));
  }

  function splitIntoSpeechChunks(text, maxLen = 175) {
    const cleaned = (text || '').replace(/\s+/g, ' ').trim();
    if (!cleaned) return [];
    const sentences = cleaned.match(/[^.!?।\n]+[.!?।]*|\S+/g) || [cleaned];
    const chunks = [];
    let current = '';
    for (const s of sentences) {
      const piece = s.trim();
      if (!piece) continue;
      if ((current + ' ' + piece).trim().length <= maxLen) {
        current = (current + ' ' + piece).trim();
      } else {
        if (current) chunks.push(current);
        current = piece.length <= maxLen ? piece : piece.slice(0, maxLen);
      }
    }
    if (current) chunks.push(current);
    return chunks;
  }

  function setBubbleDisplay(bubbleElement, text, noticeText, spokenForReplay = null) {
    if (!bubbleElement) return;
    bubbleElement.textContent = '';
    if (noticeText) {
      const badge = document.createElement('span');
      badge.className = 'demo-notice-badge';
      badge.textContent = noticeText;
      bubbleElement.appendChild(badge);
    }
    const bodySpan = document.createElement('div');
    bodySpan.textContent = text;
    bubbleElement.appendChild(bodySpan);

    if (spokenForReplay && text) {
      const replayBtn = document.createElement('button');
      replayBtn.type = 'button';
      replayBtn.className = 'msg-speak-inline';
      replayBtn.textContent = getDict().inlineListen;
      replayBtn.addEventListener('click', () => {
        speakAndStreamTogether(text, spokenForReplay, null);
      });
      bubbleElement.appendChild(replayBtn);
    }
  }

  function speakAndStreamTogether(displayText, spokenText, bubbleElement, noticeText = null) {
    stopSpeakingAndSync();
    const myToken = activeSpeechToken;
    const cleanDisplay = (displayText || '').replace(/https?:\/\/\S+/g, '').replace(/\[\d+\]/g, '').trim();
    const fullSpoken = (spokenText || cleanDisplay).trim();
    const words = cleanDisplay.split(/\s+/);
    let revealedCount = 0;

    if (bubbleElement) {
      setBubbleDisplay(bubbleElement, '', noticeText);
      bubbleElement.classList.add('speaking-now');
    }

    if (!('speechSynthesis' in window) || !fullSpoken) {
      if (bubbleElement) {
        setBubbleDisplay(bubbleElement, cleanDisplay, noticeText, fullSpoken);
        bubbleElement.classList.remove('speaking-now');
      }
      return;
    }

    const chunks = splitIntoSpeechChunks(fullSpoken);
    const langMode = langSelect.value;
    const chosenVoice = pickNaturalVoice(langMode);
    const totalSpokenChars = Math.max(1, fullSpoken.length);
    let consumedChars = 0;
    let boundaryTriggered = false;
    let speechStarted = false;

    const startGuardTimer = setTimeout(() => {
      if (myToken === activeSpeechToken && !speechStarted && bubbleElement) {
        setBubbleDisplay(bubbleElement, cleanDisplay, noticeText, fullSpoken);
        bubbleElement.classList.remove('speaking-now');
      }
    }, 1400);

    const finishSpeech = () => {
      clearTimeout(startGuardTimer);
      if (myToken !== activeSpeechToken) return;
      if (activeSyncTimer) {
        clearInterval(activeSyncTimer);
        activeSyncTimer = null;
      }
      if (bubbleElement) {
        setBubbleDisplay(bubbleElement, cleanDisplay, noticeText, fullSpoken);
        bubbleElement.classList.remove('speaking-now');
      }
      orbWrapper.classList.remove('speaking');
      soundwave.classList.remove('active');
      const dict = getDict();
      voiceStatus.textContent = dict.voiceIdle;
      voiceSubtext.textContent = dict.voiceSubIdle;
      chatMessages.scrollTop = chatMessages.scrollHeight;

      if (handsFreeMode && recognition && !isListening) {
        setTimeout(() => {
          if (myToken === activeSpeechToken && handsFreeMode && !isListening && !window.speechSynthesis.speaking) {
            try {
              const opt = langSelect.options[langSelect.selectedIndex];
              recognition.lang = opt.getAttribute('data-bcp47') || 'hi-IN';
              recognition.start();
            } catch (_) { }
          }
        }, 650);
      }
    };

    const speakChunkAt = (chunkIdx) => {
      if (myToken !== activeSpeechToken) return;
      if (chunkIdx >= chunks.length) {
        finishSpeech();
        return;
      }

      const chunkText = chunks[chunkIdx];
      const utterance = new SpeechSynthesisUtterance(chunkText);
      if (chosenVoice) {
        utterance.voice = chosenVoice;
        utterance.lang = chosenVoice.lang;
      } else {
        utterance.lang = langMode === 'English' ? 'en-IN' : langMode === 'Marathi' ? 'mr-IN' : 'hi-IN';
      }
      utterance.rate = 0.96;
      utterance.pitch = 1.02;

      utterance.onboundary = (event) => {
        if (myToken !== activeSpeechToken) return;
        if (event.name === 'word' && bubbleElement && words.length > 0) {
          boundaryTriggered = true;
          const globalPos = consumedChars + (event.charIndex || 0) + 8;
          const progressRatio = Math.min(1, globalPos / totalSpokenChars);
          revealedCount = Math.min(words.length, Math.max(revealedCount + 1, Math.ceil(progressRatio * words.length)));
          setBubbleDisplay(bubbleElement, words.slice(0, revealedCount).join(' '), noticeText);
          chatMessages.scrollTop = chatMessages.scrollHeight;
        }
      };

      utterance.onstart = () => {
        if (myToken !== activeSpeechToken) return;
        speechStarted = true;
        clearTimeout(startGuardTimer);
        if (chunkIdx === 0) {
          orbWrapper.classList.remove('listening');
          orbWrapper.classList.add('speaking');
          soundwave.classList.add('active');
          voiceStatus.textContent = langMode === 'English'
            ? '🗣️ VayuMitra is Speaking...'
            : langMode === 'Marathi'
              ? '🗣️ वायुमित्र बोलत आहे...'
              : '🗣️ वायुमित्र बोल रहा है...';

          const avgMsPerWord = Math.max(180, Math.min(340, (totalSpokenChars * 62) / Math.max(1, words.length)));
          activeSyncTimer = setInterval(() => {
            if (myToken !== activeSpeechToken) return;
            if (!boundaryTriggered && bubbleElement && revealedCount < words.length) {
              revealedCount++;
              setBubbleDisplay(bubbleElement, words.slice(0, revealedCount).join(' '), noticeText);
              chatMessages.scrollTop = chatMessages.scrollHeight;
            }
          }, avgMsPerWord);
        }
      };

      utterance.onend = () => {
        if (myToken !== activeSpeechToken) return;
        consumedChars += chunkText.length + 1;
        speakChunkAt(chunkIdx + 1);
      };
      utterance.onerror = () => finishSpeech();
      window.speechSynthesis.speak(utterance);
    };

    speakChunkAt(0);
  }

  // ---------------------------------------------------------------------------
  // 8. Speech Recognition
  // ---------------------------------------------------------------------------
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (SpeechRecognition) {
    recognition = new SpeechRecognition();
    recognition.continuous = false;
    recognition.interimResults = true;

    recognition.onstart = () => {
      isListening = true;
      stopSpeakingAndSync();
      orbWrapper.classList.add('listening');
      soundwave.classList.add('active');
      const lang = langSelect.value;
      voiceStatus.textContent = lang === 'English'
        ? '👂 Listening... Speak Now'
        : lang === 'Marathi'
          ? '👂 मी ऐकत आहे... बोला'
          : '👂 मैं सुन रहा हूँ... बोलिए';

      liveUserBubble = document.createElement('div');
      liveUserBubble.className = 'msg user live-hearing';
      liveUserBubble.textContent = '🎙️ ...';
      chatMessages.appendChild(liveUserBubble);
      chatMessages.scrollTop = chatMessages.scrollHeight;
    };

    recognition.onresult = (event) => {
      let transcript = '';
      for (let i = event.resultIndex; i < event.results.length; i++) {
        transcript += event.results[i][0].transcript;
      }
      chatInput.value = transcript;
      if (liveUserBubble) {
        liveUserBubble.textContent = transcript || '🎙️ ...';
        chatMessages.scrollTop = chatMessages.scrollHeight;
      }

      if (event.results[event.results.length - 1].isFinal) {
        const finalWords = transcript.trim();
        if (liveUserBubble) { liveUserBubble.remove(); liveUserBubble = null; }
        stopListeningUI();
        if (finalWords) {
          chatInput.value = '';
          sendMessage(finalWords, consumePendingPhoto());
        }
      }
    };

    recognition.onerror = (event) => {
      if (liveUserBubble) { liveUserBubble.remove(); liveUserBubble = null; }
      stopListeningUI();
      const errCode = event && event.error ? event.error : 'unknown';
      if (errCode === 'not-allowed' || errCode === 'service-not-allowed') {
        handsFreeMode = false;
        handsfreeBtn.classList.remove('call-active');
        handsfreeBtn.setAttribute('aria-pressed', 'false');
        handsfreeBtn.textContent = getDict().handsfreeOff;
        voiceStatus.textContent = '🚫 Mic Permission Blocked';
      }
    };

    recognition.onend = () => {
      if (liveUserBubble) { liveUserBubble.remove(); liveUserBubble = null; }
      stopListeningUI();
    };
  }

  function stopListeningUI() {
    isListening = false;
    orbWrapper.classList.remove('listening');
    if (!orbWrapper.classList.contains('speaking')) {
      soundwave.classList.remove('active');
      voiceStatus.textContent = getDict().voiceIdle;
    }
  }

  // ---------------------------------------------------------------------------
  // 9. Camera Compression & Preview
  // ---------------------------------------------------------------------------
  function compressImageFile(file, maxDimension = 1280, quality = 0.82) {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onerror = reject;
      reader.onload = () => {
        const img = new Image();
        img.onerror = () => {
          const rawUrl = reader.result;
          resolve({ dataUrl: rawUrl, base64Data: rawUrl.split(',')[1], mimeType: file.type || 'image/jpeg', sizeKb: Math.round(file.size / 1024) });
        };
        img.onload = () => {
          let { width, height } = img;
          if (width > maxDimension || height > maxDimension) {
            const scale = maxDimension / Math.max(width, height);
            width = Math.round(width * scale);
            height = Math.round(height * scale);
          }
          const canvas = document.createElement('canvas');
          canvas.width = width;
          canvas.height = height;
          canvas.getContext('2d').drawImage(img, 0, 0, width, height);
          const compressedUrl = canvas.toDataURL('image/jpeg', quality);
          const base64Data = compressedUrl.split(',')[1];
          const sizeKb = Math.max(1, Math.round((base64Data.length * 3) / 4 / 1024));
          resolve({ dataUrl: compressedUrl, base64Data, mimeType: 'image/jpeg', sizeKb });
        };
        img.src = reader.result;
      };
      reader.readAsDataURL(file);
    });
  }

  function clearPendingPhoto() {
    pendingPhoto = null;
    pendingPhotoBar.hidden = true;
    pendingPhotoThumb.removeAttribute('src');
  }

  function consumePendingPhoto() {
    const photo = pendingPhoto;
    clearPendingPhoto();
    return photo;
  }

  function getDefaultPhotoPrompt(lang) {
    if (lang === 'English') return 'Look at this photo and tell me in simple words what air safety precautions we should take.';
    if (lang === 'Marathi') return 'हा फोटो पाहून अगदी सोप्या मराठीत सांगा की हवेसाठी किंवा खोलीसाठी काय काळजी घ्यावी?';
    if (lang === 'Hindi') return 'यह फोटो देखकर बिल्कुल आसान भाषा में बताओ कि हवा या कमरे में क्या सावधानी रखें?';
    return 'Yeh photo dekhkar bilkul aasan bhasha mein batao ki hawa ya kamre mein kya savdhani rakhein?';
  }

  // ---------------------------------------------------------------------------
  // 10. Chat Messaging + Offline Fallback
  // ---------------------------------------------------------------------------
  function generateSmartDemoResponse(city, lang) {
    const aqi = liveAqiValue ?? 150;
    const cigs = Math.max(1, Math.round((livePm25Value ?? 66) / 22));
    if (lang === 'English') {
      const r = `Right now in ${city}, AQI is ${aqi} (about ${cigs} cigarettes of smoke). Wear an N95 mask or clean 3-layer cotton cloth outdoors, and use a wet mop at home.`;
      return { reply: r, spoken_summary: r };
    }
    if (lang === 'Marathi') {
      const r = `आत्ता ${city} मध्ये हवेत धूर जास्त आहे (न पिता ${cigs} सिगारेट बरोबर). बाहेर जाताना मास्क किंवा सुती रुमाल बांधा आणि घरात ओला पोछा मारा.`;
      return { reply: r, spoken_summary: r };
    }
    if (lang === 'Hindi') {
      const r = `आज ${city} की हवा में बिना पिए ${cigs} सिगरेट बराबर धुआँ है। बाहर मास्क या साफ सूती गमछा बाँधें और घर में गीला पोछा लगाएँ।`;
      return { reply: r, spoken_summary: r };
    }
    return {
      reply: `Aaj ${city} ki hawa mein bina piye ${cigs} cigarette barabar dhuan hai. Bahar N95 mask ya saaf suti gamchha bandhein aur ghar mein geela pochha lagayein!`,
      spoken_summary: `आज ${city} की हवा में बिना पिए ${cigs} सिगरेट बराबर धुआँ है। बाहर मास्क या साफ सूती गमछा बाँधें और घर में गीला पोछा लगाएँ।`
    };
  }

  async function sendMessage(text, photoAttachment = null) {
    if (!text && !photoAttachment) return;
    const finalPrompt = text || getDefaultPhotoPrompt(langSelect.value);
    stopSpeakingAndSync();

    const userDiv = document.createElement('div');
    userDiv.className = 'msg user';
    if (photoAttachment && photoAttachment.dataUrl) {
      const img = document.createElement('img');
      img.src = photoAttachment.dataUrl;
      img.alt = 'Uploaded sky or room photo';
      img.className = 'uploaded-preview';
      userDiv.appendChild(img);
    }
    const span = document.createElement('span');
    span.textContent = finalPrompt;
    userDiv.appendChild(span);
    chatMessages.appendChild(userDiv);
    chatMessages.scrollTop = chatMessages.scrollHeight;

    const botDiv = document.createElement('div');
    botDiv.className = 'msg assistant speaking-now';
    botDiv.textContent = '•••';
    chatMessages.appendChild(botDiv);
    chatMessages.scrollTop = chatMessages.scrollHeight;

    sendButton.disabled = true;
    const activeCity = (cityInput.value && cityInput.value !== 'Locating...') ? cityInput.value.trim() : 'Delhi NCR';
    voiceStatus.textContent = langSelect.value === 'English'
      ? `🔍 Checking for ${activeCity}...`
      : `🔍 ${activeCity} ke liye salah taiyar ho rahi hai...`;

    const payload = {
      message: finalPrompt,
      city: activeCity,
      coordinates: liveCoordinates,
      live_aqi: liveAqiValue,
      live_pm25: livePm25Value,
      weather_summary: liveWeatherSummary,
      profile: selectedProfile,
      mode: modeSelect.value,
      language: langSelect.value,
      image_base64: photoAttachment ? photoAttachment.base64Data : null,
      image_mime_type: photoAttachment ? photoAttachment.mimeType : null,
      previous_interaction_id: previousInteractionId
    };

    try {
      const res = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      if (!res.ok) {
        const demo = generateSmartDemoResponse(activeCity, payload.language);
        lastDisplayReply = demo.reply;
        lastSpokenReply = demo.spoken_summary;
        speakAndStreamTogether(demo.reply, demo.spoken_summary, botDiv, '⚠️ Demo Fallback');
        return;
      }
      const data = await res.json();
      previousInteractionId = data.interaction_id || previousInteractionId;
      lastDisplayReply = data.reply;
      lastSpokenReply = data.spoken_summary;
      speakAndStreamTogether(data.reply, data.spoken_summary, botDiv);
    } catch (_) {
      const demo = generateSmartDemoResponse(activeCity, payload.language);
      lastDisplayReply = demo.reply;
      lastSpokenReply = demo.spoken_summary;
      speakAndStreamTogether(demo.reply, demo.spoken_summary, botDiv, '⚠️ Offline Fallback');
    } finally {
      sendButton.disabled = false;
    }
  }

  // ---------------------------------------------------------------------------
  // 11. Event Bindings
  // ---------------------------------------------------------------------------
  meterSpeakBtn.addEventListener('click', () => {
    const fullSpoken = `${lastMeterSpoken} ${lastClockSpoken}`.trim();
    speakAndStreamTogether(fullSpoken, fullSpoken, null);
  });

  emergencyBtn.addEventListener('click', () => {
    const dict = getDict();
    const botDiv = document.createElement('div');
    botDiv.className = 'msg assistant speaking-now';
    chatMessages.appendChild(botDiv);
    chatMessages.scrollTop = chatMessages.scrollHeight;
    lastDisplayReply = dict.emergencyText;
    lastSpokenReply = dict.emergencySpoken;
    speakAndStreamTogether(dict.emergencyText, dict.emergencySpoken, botDiv);
  });

  clockSpeakBtn.addEventListener('click', () => {
    speakAndStreamTogether(lastClockSpoken, lastClockSpoken, null);
  });

  tileMask.addEventListener('click', () => speakAndStreamTogether(tileSpoken.mask, tileSpoken.mask, null));
  tileWindow.addEventListener('click', () => speakAndStreamTogether(tileSpoken.window, tileSpoken.window, null));
  tileFamily.addEventListener('click', () => speakAndStreamTogether(tileSpoken.family, tileSpoken.family, null));
  tileHome.addEventListener('click', () => speakAndStreamTogether(tileSpoken.home, tileSpoken.home, null));

  cityInput.addEventListener('keydown', (event) => {
    if (event.key === 'Enter') {
      event.preventDefault();
      cityInput.blur();
      searchTypedLocation();
    }
  });
  cityInput.addEventListener('blur', searchTypedLocation);
  refreshGpsBtn.addEventListener('click', detectLiveLocation);

  document.querySelectorAll('[data-preset]').forEach((btn) => {
    btn.addEventListener('click', () => applyRoutinePreset(btn.getAttribute('data-preset')));
  });
  document.querySelectorAll('[data-km]').forEach((btn) => {
    btn.addEventListener('click', () => { commuteKmEl.value = btn.getAttribute('data-km'); });
  });
  document.querySelectorAll('[data-hrs]').forEach((btn) => {
    btn.addEventListener('click', () => { outdoorHoursEl.value = btn.getAttribute('data-hrs'); });
  });
  routineForm.addEventListener('submit', handleRoutineSubmit);

  speakPlanBtn.addEventListener('click', () => {
    if (lastRoutinePlan && lastRoutinePlan.spoken_summary) {
      speakAndStreamTogether(lastRoutinePlan.spoken_summary, lastRoutinePlan.spoken_summary, null);
    }
  });

  sharePlanBtn.addEventListener('click', () => {
    if (!lastRoutinePlan) return;
    const m = lastRoutinePlan.metrics || {};
    const shareText =
      `🌬️ *VayuMitra Family Air Plan (${lastRoutinePlan.city})*\n` +
      `📊 -${m.exposure_reduction_pct}% smoke • ${m.weekly_co2_saved_kg} kg CO₂ saved/week\n\n` +
      `🌱 *Steps:*\n- ${(lastRoutinePlan.low_emission_steps || []).join('\n- ')}\n\n` +
      `🏠 *Home Hacks:*\n- ${(lastRoutinePlan.indoor_air_hacks || []).join('\n- ')}`;
    window.open(`https://wa.me/?text=${encodeURIComponent(shareText)}`, '_blank', 'noopener,noreferrer');
  });

  document.querySelectorAll('.profile-btn').forEach((btn) => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.profile-btn').forEach((b) => {
        b.classList.remove('active');
        b.setAttribute('aria-pressed', 'false');
      });
      btn.classList.add('active');
      btn.setAttribute('aria-pressed', 'true');
      selectedProfile = btn.getAttribute('data-profile');
    });
  });

  askProfileBtn.addEventListener('click', () => {
    const lang = langSelect.value;
    const prompt = lang === 'English'
      ? `What are the top 2–3 most important air safety precautions today for "${selectedProfile}"?`
      : lang === 'Marathi'
        ? `आजच्या धुरात "${selectedProfile}" साठी सर्वात महत्त्वाची 2-3 काळजी काय घ्यावी?`
        : lang === 'Hindi'
          ? `आज के धुएँ में "${selectedProfile}" के लिए सबसे ज़रूरी 2-3 सावधानियाँ क्या हैं?`
          : `Aaj ke dhuein mein "${selectedProfile}" ke liye sabse zaroori 2-3 savdhaniyan kya hain?`;
    sendMessage(prompt);
  });

  newChatBtn.addEventListener('click', () => {
    stopSpeakingAndSync();
    clearPendingPhoto();
    previousInteractionId = null;
    chatMessages.innerHTML = '';
    const dict = getDict();
    const welcome = document.createElement('div');
    welcome.className = 'msg assistant';
    welcome.id = 'initial-welcome-msg';
    welcome.textContent = dict.welcomeMsg;
    chatMessages.appendChild(welcome);
    lastDisplayReply = welcome.textContent;
    lastSpokenReply = welcome.textContent;
  });

  handsfreeBtn.addEventListener('click', () => {
    handsFreeMode = !handsFreeMode;
    handsfreeBtn.setAttribute('aria-pressed', String(handsFreeMode));
    const dict = getDict();
    if (handsFreeMode) {
      handsfreeBtn.classList.add('call-active');
      handsfreeBtn.textContent = dict.handsfreeOn;
      if (recognition && !isListening && !window.speechSynthesis.speaking) {
        const opt = langSelect.options[langSelect.selectedIndex];
        recognition.lang = opt.getAttribute('data-bcp47') || 'hi-IN';
        recognition.start();
      }
    } else {
      handsfreeBtn.classList.remove('call-active');
      handsfreeBtn.textContent = dict.handsfreeOff;
      if (recognition && isListening) recognition.stop();
    }
  });

  micBtn.addEventListener('click', () => {
    if (!recognition) {
      alert('Please open in Google Chrome or Microsoft Edge for voice input.');
      return;
    }
    if (isListening) {
      recognition.stop();
    } else {
      const opt = langSelect.options[langSelect.selectedIndex];
      recognition.lang = opt.getAttribute('data-bcp47') || 'hi-IN';
      recognition.start();
    }
  });

  stopTtsBtn.addEventListener('click', () => {
    handsFreeMode = false;
    handsfreeBtn.classList.remove('call-active');
    handsfreeBtn.setAttribute('aria-pressed', 'false');
    handsfreeBtn.textContent = getDict().handsfreeOff;
    stopSpeakingAndSync();
  });

  replayTtsBtn.addEventListener('click', () => {
    if (lastDisplayReply || lastSpokenReply) {
      speakAndStreamTogether(lastDisplayReply || lastSpokenReply, lastSpokenReply, null);
    }
  });

  whatsappBtn.addEventListener('click', () => {
    const city = cityInput.value || 'Delhi NCR';
    const aqi = liveAqiValue ?? 150;
    const cigs = Math.max(1, Math.round((livePm25Value ?? 66) / 22));
    const shareText =
      `🌬️ *VayuMitra Suraksha Alert (${city})*\n` +
      `🚦 AQI ${aqi} (~${cigs} cigarettes/day smoke)\n\n` +
      `💡 ${lastDisplayReply}`;
    window.open(`https://wa.me/?text=${encodeURIComponent(shareText)}`, '_blank', 'noopener,noreferrer');
  });

  heroPhotoBtn.addEventListener('click', () => photoInput.click());
  cameraBtn.addEventListener('click', () => photoInput.click());
  removePhotoBtn.addEventListener('click', clearPendingPhoto);

  photoInput.addEventListener('change', async (e) => {
    const file = e.target.files && e.target.files[0];
    photoInput.value = '';
    if (!file) return;
    try {
      const compressed = await compressImageFile(file);
      pendingPhoto = compressed;
      pendingPhotoThumb.src = compressed.dataUrl;
      pendingPhotoInfo.textContent = `Photo (${compressed.sizeKb} KB)`;
      pendingPhotoBar.hidden = false;
      // Immediately send if user tapped hero photo button for effortless non-reader flow
      sendMessage('', consumePendingPhoto());
    } catch (_) {
      alert('Could not process the selected image.');
    }
  });

  chatInput.addEventListener('keydown', (event) => {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      if (event.isComposing || event.keyCode === 229) return;
      chatForm.requestSubmit();
    }
  });

  chatForm.addEventListener('submit', (event) => {
    event.preventDefault();
    const text = chatInput.value.trim();
    const attached = consumePendingPhoto();
    if (text || attached) {
      chatInput.value = '';
      sendMessage(text, attached);
    }
  });

  document.querySelectorAll('[data-prompt]').forEach((el) => {
    el.addEventListener('click', () => {
      const promptText = el.getAttribute('data-prompt');
      if (el.id === 'pillar-4') modeSelect.value = 'detailed_plan';
      sendMessage(promptText);
    });
  });

  if ('speechSynthesis' in window) {
    window.speechSynthesis.onvoiceschanged = () => {
      const v = pickNaturalVoice(langSelect.value);
      if (v) voiceIndicatorPill.textContent = `🟢 ${v.name.replace(/Microsoft |Online \(Natural\) - /g, '')}`;
    };
  }

  langSelect.addEventListener('change', () => {
    applyLanguageToUI(langSelect.value);
    const v = pickNaturalVoice(langSelect.value);
    if (v) voiceIndicatorPill.textContent = `🟢 ${v.name.replace(/Microsoft |Online \(Natural\) - /g, '')}`;
    if (liveAqiValue !== null && livePm25Value !== null) {
      renderTrafficLightMeter(currentCityLabel, liveAqiValue, livePm25Value);
      updatePictureTiles(liveAqiValue, livePm25Value);
    }
    updateSafeWindowClock();
  });

  // Two-state Day/Night color-scheme toggle (persists only when overriding OS preference)
  const themeToggleBtn = $('theme-toggle-btn');
  const colorSchemeMeta = document.querySelector('meta[name="color-scheme"]');
  if (themeToggleBtn && colorSchemeMeta) {
    const getSystemScheme = () => (window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
    const getEffectiveScheme = () => {
      const content = colorSchemeMeta.getAttribute('content');
      return (content === 'light' || content === 'dark') ? content : getSystemScheme();
    };
    themeToggleBtn.addEventListener('click', () => {
      const target = getEffectiveScheme() === 'dark' ? 'light' : 'dark';
      const system = getSystemScheme();
      try {
        if (target === system) {
          localStorage.removeItem('color-scheme');
          colorSchemeMeta.setAttribute('content', 'light dark');
        } else {
          localStorage.setItem('color-scheme', target);
          colorSchemeMeta.setAttribute('content', target);
        }
      } catch (_) {
        colorSchemeMeta.setAttribute('content', target);
      }
    });
    window.addEventListener('storage', (event) => {
      if (event.key === 'color-scheme') {
        colorSchemeMeta.setAttribute('content', event.newValue || 'light dark');
      }
    });
  }

  window.addEventListener('DOMContentLoaded', () => {
    initAccessibleValidation(routineForm);
    applyLanguageToUI(langSelect.value);
    checkServerHealth();
    updateSafeWindowClock();
    setInterval(updateSafeWindowClock, 60000);
    detectLiveLocation();
  });
})();
