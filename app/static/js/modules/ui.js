/**
 * VoxCorr — module ui.js
 * Machine à états pour la page d'enregistrement.
 * États : idle → recording → stopped → processing → done → published
 */

export const UI = {
  // ── Sélecteurs centralisés ─────────────────────────────────────────────────
  get btnStart()      { return document.getElementById('btn-start'); },
  get btnStop()       { return document.getElementById('btn-stop'); },
  get btnSave()       { return document.getElementById('btn-save'); },
  get btnPublish()    { return document.getElementById('btn-publish'); },
  get transcript()    { return document.getElementById('transcription'); },
  get interim()       { return document.getElementById('interim'); },
  get statusText()    { return document.getElementById('recording-status'); },
  get synthPanel()    { return document.getElementById('ai-result-section'); },
  get synthText()     { return document.getElementById('ai-formatted-text'); },
  get gradesList()    { return document.getElementById('ai-grades-list'); },
  get qrPanel()       { return document.getElementById('qr-panel'); },
  get qrImg()         { return document.getElementById('qr-img'); },
  get qrUrl()         { return document.getElementById('qr-url'); },
  get totalScore()    { return document.getElementById('total-score'); },
  get waveformBars()  { return [...document.querySelectorAll('.vox-waveform-bar')]; },
  get scoreInputs()   { return [...document.querySelectorAll('.score-input')]; },

  show(el) { el?.classList.remove('d-none'); },
  hide(el) { el?.classList.add('d-none'); },

  setStatus(html) { if (this.statusText) this.statusText.innerHTML = html; },

  setState(state, payload = {}) {
    const S = {
      idle: () => {
        this.show(this.btnStart); this.hide(this.btnStop);
        this.hide(this.btnSave);  this.hide(this.btnPublish);
        this.setStatus('<span class="text-muted">Prêt à enregistrer…</span>');
        this.btnStart?.classList.remove('recording');
      },
      recording: () => {
        this.hide(this.btnStart); this.show(this.btnStop);
        this.hide(this.btnSave);
        this.setStatus('<span class="text-danger fw-bold">⬤ Enregistrement en cours…</span>');
        this.btnStart?.classList.add('recording');
      },
      stopped: () => {
        this.show(this.btnStart); this.hide(this.btnStop);
        this.show(this.btnSave);
        this.setStatus('Enregistrement terminé. Vérifiez la transcription puis sauvegardez.');
        this.btnStart?.classList.remove('recording');
      },
      processing: () => {
        this.hide(this.btnSave);
        this.setStatus('<span class="text-warning">⏳ Analyse Mistral en cours…</span>');
        this.show(this.synthPanel);
        if (this.synthText) this.synthText.innerHTML =
          '<div class="d-flex gap-2 align-items-center text-muted py-2">' +
          '<div class="spinner-border spinner-border-sm"></div>Mistral rédige la synthèse…</div>';
      },
      done: () => {
        this.show(this.btnPublish);
        this.setStatus('<span class="text-success fw-bold">✓ Correction analysée — prête à publier</span>');
        if (payload.structured_text && this.synthText)
          this.synthText.innerHTML = payload.structured_text;
        if (payload.total_score != null && this.totalScore)
          this.totalScore.textContent = payload.total_score;
      },
      published: () => {
        this.hide(this.btnPublish);
        this.setStatus('<span class="text-success fw-bold">✓ Publié — QR code disponible</span>');
        this.show(this.qrPanel);
        if (payload.qr  && this.qrImg) this.qrImg.src = payload.qr;
        if (payload.url && this.qrUrl) { this.qrUrl.href = payload.url; this.qrUrl.textContent = payload.url; }
      },
    };
    S[state]?.call(this);
  },

  collectScores() {
    return this.scoreInputs
      .map(inp => ({
        question_id: parseInt(inp.dataset.qid, 10),
        score:       parseFloat(inp.value) || 0,
      }))
      .filter(s => s.score > 0);   // ← ne transmet que les notes saisies manuellement
  },
};
