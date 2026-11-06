/**
 * VoxCorr — module ui.js
 * Machine à états de la page de correction.
 * États : idle → recording → stopped → processing → done → published
 */
export const UI = {
  get btnStart()     { return document.getElementById('btn-start'); },
  get btnStop()      { return document.getElementById('btn-stop'); },
  get btnSave()      { return document.getElementById('btn-save'); },
  get btnPublish()   { return document.getElementById('btn-publish'); },
  get btnEditSynth() { return document.getElementById('btn-edit-synth'); },
  get transcript()   { return document.getElementById('transcription'); },
  get interim()      { return document.getElementById('interim'); },
  get statusText()   { return document.getElementById('recording-status'); },
  get synthPanel()   { return document.getElementById('ai-result-section'); },
  get synthText()    { return document.getElementById('ai-formatted-text'); },
  get qrPanel()      { return document.getElementById('qr-panel'); },
  get qrImg()        { return document.getElementById('qr-img'); },
  get qrUrl()        { return document.getElementById('qr-url'); },
  get navPanel()     { return document.getElementById('nav-correction'); },
  get totalScore()   { return document.getElementById('total-score'); },
  get waveformBars() { return [...document.querySelectorAll('.rec-waveform-bar')]; },
  get scoreInputs()  { return [...document.querySelectorAll('.score-input')]; },

  show(el) { el?.classList.remove('d-none'); },
  hide(el) { el?.classList.add('d-none'); },
  setStatus(html) { if (this.statusText) this.statusText.innerHTML = html; },

  setState(state, payload = {}) {
    const S = {
      idle: () => {
        this.show(this.btnStart);
        this.hide(this.btnStop);
        this.hide(this.btnSave);
        this.hide(this.btnPublish);
        this.setStatus('<span class="text-muted">Prêt à enregistrer…</span>');
        this.btnStart?.classList.remove('recording');
      },
      recording: () => {
        this.hide(this.btnStart);
        this.show(this.btnStop);
        this.hide(this.btnSave);
        this.setStatus('<span class="text-danger fw-bold">● Enregistrement en cours…</span>');
        this.btnStart?.classList.add('recording');
      },
      stopped: () => {
        this.show(this.btnStart);
        this.hide(this.btnStop);
        this.show(this.btnSave);
        this.setStatus('Enregistrement terminé. Vérifiez la transcription puis lancez l\'analyse.');
        this.btnStart?.classList.remove('recording');
      },
      processing: () => {
        this.hide(this.btnSave);
        this.hide(this.btnEditSynth);
        this.setStatus('<span class="text-warning">⏳ Analyse en cours…</span>');
        this.show(this.synthPanel);
        if (this.synthText) {
          this.synthText.innerHTML =
            '<div class="d-flex gap-2 align-items-center py-2">' +
            '<div class="spinner-border spinner-border-sm"></div>L\'IA rédige la synthèse…</div>';
        }
      },
      done: () => {
        this.show(this.btnPublish);
        this.show(this.btnEditSynth);
        this.setStatus('<span class="text-success fw-bold">✓ Analyse terminée : vérifiez les notes puis publiez</span>');
        this.show(this.synthPanel);
        if (payload.structured_text && this.synthText) this.synthText.innerHTML = payload.structured_text;
        if (payload.total_score != null && this.totalScore) {
          this.totalScore.textContent = Number(payload.total_score).toFixed(1);
        }
      },
      published: () => {
        this.hide(this.btnPublish);
        this.setStatus('<span class="text-success fw-bold">✓ Publié</span>');
        this.show(this.qrPanel);
        if (payload.qr && this.qrImg) this.qrImg.src = payload.qr;
        if (payload.url && this.qrUrl) {
          this.qrUrl.href = payload.url;
          this.qrUrl.textContent = payload.url;
        }
        this.show(this.navPanel);
      },
    };
    S[state]?.call(this);
  },

  /** Notes tapées à la main (et seulement elles), prêtes à être envoyées. */
  collectManual() {
    return this.scoreInputs
      .filter(i => i.dataset.manual === '1' && i.value !== '')
      .map(i => ({ question_id: parseInt(i.dataset.qid, 10), score: parseFloat(i.value) || 0 }));
  },

  clearScores() {
    this.scoreInputs.forEach(i => { i.value = ''; delete i.dataset.manual; });
  },

  clearManualFlags() {
    this.scoreInputs.forEach(i => { delete i.dataset.manual; });
  },
};