class VoxRecorder {
  constructor(opts = {}) {
    this.onTranscript  = opts.onTranscript  || (() => {});
    this.onAudioReady  = opts.onAudioReady  || (() => {});
    this.onStateChange = opts.onStateChange || (() => {});
    this.isRecording = false; this.recognition = null; this.mediaRec = null;
    this.audioChunks = []; this.stream = null; this.analyser = null;
    this.animFrame = null; this.transcript = '';
    this._fatal = false;
  }

  _warn(title, message) { window.voxShowError?.(title, message); }

  _initRecognition() {
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SR) {
      this._warn('Dictée non disponible',
        "Ce navigateur ne propose pas la transcription en direct. Utilisez Chrome, ou tapez votre correction dans la zone de texte (l'audio sera quand même enregistré).");
      return null;
    }
    const r = new SR();
    r.lang = 'fr-FR'; r.continuous = true; r.interimResults = true;
    r.onresult = (e) => {
      let interim = '';
      for (let i = e.resultIndex; i < e.results.length; i++) {
        const t = e.results[i][0].transcript;
        if (e.results[i].isFinal) this.transcript += t + ' '; else interim = t;
      }
      this.onTranscript(this.transcript, interim);
    };
    r.onerror = (e) => {
      console.warn(e.error);
      if (e.error === 'no-speech' || e.error === 'aborted') return;
      this._fatal = true;
      if (e.error === 'not-allowed' || e.error === 'service-not-allowed') {
        this._warn('Dictée bloquée', "Autorisez le micro (cadenas à gauche de l'adresse), puis recommencez.");
      } else if (e.error === 'network') {
        this._warn('Dictée indisponible', "Le service vocal du navigateur est injoignable. Vérifiez la connexion, ou essayez Chrome. L'audio reste enregistré : vous pouvez taper le texte à la main.");
      } else {
        this._warn('Dictée interrompue', 'Erreur : ' + e.error);
      }
    };
    r.onend = () => {
      if (this.isRecording && !this._fatal) setTimeout(() => { try { r.start(); } catch (_) {} }, 200);
    };
    return r;
  }

  _startWaveform(bars) {
    if (!bars.length) return;
    const data = new Uint8Array(this.analyser.frequencyBinCount);
    const draw = () => {
      this.analyser.getByteFrequencyData(data);
      const step = Math.floor(data.length / bars.length) || 1;
      bars.forEach((b, i) => {
        const v = data[i * step] || 0;
        b.style.height = Math.max(4, (v / 255) * 52) + 'px';
        b.style.opacity = 0.4 + (v / 255) * 0.6;
      });
      this.animFrame = requestAnimationFrame(draw);
    };
    draw();
  }

  _stopWaveform(bars) {
    if (this.animFrame) cancelAnimationFrame(this.animFrame);
    bars?.forEach(b => { b.style.height = '6px'; b.style.opacity = '.4'; });
  }

  async start(bars = []) {
    if (this.isRecording) return;
    try {
      this.stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch (e) {
      this._warn('Micro inaccessible', 'Vérifiez que votre microphone est bien branché et autorisé dans les paramètres du navigateur.');
      return;
    }
    const ctx = new AudioContext();
    const src = ctx.createMediaStreamSource(this.stream);
    this.analyser = ctx.createAnalyser(); this.analyser.fftSize = 256; src.connect(this.analyser);
    this._startWaveform(bars);

    const mime = MediaRecorder.isTypeSupported('audio/webm;codecs=opus') ? 'audio/webm;codecs=opus' : 'audio/webm';
    this.mediaRec = new MediaRecorder(this.stream, { mimeType: mime });
    this.audioChunks = [];
    this.mediaRec.ondataavailable = e => { if (e.data.size > 0) this.audioChunks.push(e.data); };
    this.mediaRec.onstop = () => { this.onAudioReady(new Blob(this.audioChunks, { type: mime })); };
    this.mediaRec.start(200);

    this._fatal = false; this.transcript = '';
    this.recognition = this._initRecognition();
    if (this.recognition) { try { this.recognition.start(); } catch (_) {} }
    this.isRecording = true;
    this.onStateChange('recording');
  }

  stop(bars = []) {
    this.isRecording = false;
    if (this.recognition) { try { this.recognition.stop(); } catch (_) {} }
    if (this.mediaRec && this.mediaRec.state !== 'inactive') this.mediaRec.stop();
    if (this.stream) this.stream.getTracks().forEach(t => t.stop());
    this._stopWaveform(bars);
    this.onStateChange('stopped');
  }
}
window.VoxRecorder = VoxRecorder;

/* ── Mode hors-ligne : sauvegarde locale puis envoi au retour du réseau ── */
const PENDING_KEY = 'pendingCorrections';
const readPending  = () => { try { return JSON.parse(localStorage.getItem(PENDING_KEY) || '[]'); } catch (_) { return []; } };
const writePending = (list) => localStorage.setItem(PENDING_KEY, JSON.stringify(list));
const csrfToken    = () => document.querySelector('meta[name="csrf-token"]')?.content || '';

function blobToDataURL(blob) {
  return new Promise((resolve, reject) => {
    const r = new FileReader();
    r.onload = () => resolve(r.result);
    r.onerror = reject;
    r.readAsDataURL(blob);
  });
}

async function saveCorrectionOffline(correctionData, audioBlob) {
  const id = Date.now();
  try {
    const list = readPending();
    list.push({ id, data: correctionData, timestamp: new Date().toISOString() });
    writePending(list);
    if (audioBlob) localStorage.setItem(`pending_audio_${id}`, await blobToDataURL(audioBlob));
  } catch (e) { console.warn('Stockage local plein ou indisponible', e); }
  return id;
}
window.saveCorrectionOffline = saveCorrectionOffline;

async function syncPendingCorrections() {
  if (!navigator.onLine) return;
  for (const pending of readPending()) {
    try {
      const res = await fetch('/teacher/api/correction/save', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken() },
        body: JSON.stringify(pending.data),
      });
      if (!res.ok) continue;
      const saved = await res.json();

      const audioURL = localStorage.getItem(`pending_audio_${pending.id}`);
      if (audioURL && saved.correction_id) {
        const blob = await (await fetch(audioURL)).blob();
        const fd = new FormData();
        fd.append('audio', blob, 'correction.webm');
        await fetch(`/teacher/api/correction/${saved.correction_id}/audio`, {
          method: 'POST', headers: { 'X-CSRFToken': csrfToken() }, body: fd,
        });
      }
      localStorage.removeItem(`pending_audio_${pending.id}`);
      writePending(readPending().filter(p => p.id !== pending.id));
      console.log(`Correction ${pending.id} synchronisée`);
    } catch (err) { console.error('Erreur synchronisation', err); }
  }
}

window.addEventListener('online', syncPendingCorrections);
setTimeout(syncPendingCorrections, 3000);