/**
 * VoxCorr — record_page.js
 * Point d'entrée unique de la page d'enregistrement.
 * Importe les modules, orchestre le flux. Aucune logique métier ici.
 *
 * window.VC = { studentId, assignmentId, correctionId } injecté par Jinja2.
 */

import { UI }  from './modules/ui.js';
import { api } from './modules/api.js';

const CTX = window.VC || {};

let recorder     = null;
let audioBlob    = null;
let correctionId = CTX.correctionId || null;
let pollTimer    = null;

document.addEventListener('DOMContentLoaded', () => {
  // recorder.js est chargé en script classique → window.VoxRecorder disponible
  recorder = new window.VoxRecorder({
    onTranscript:  (final, interim) => {
      if (UI.transcript) UI.transcript.value = final;
      if (UI.interim)    UI.interim.textContent = interim;
    },
    onAudioReady:  (blob) => { audioBlob = blob; UI.setState('stopped'); },
    onStateChange: (state) => { if (state === 'recording') UI.setState('recording'); },
  });

  UI.setState('idle');

  UI.btnStart?.addEventListener('click', () => recorder.start(UI.waveformBars));
  UI.btnStop?.addEventListener('click',  () => recorder.stop(UI.waveformBars));

  UI.btnSave?.addEventListener('click', async () => {
    const text = UI.transcript?.value?.trim() || '';
    if (!text) { alert('La transcription est vide.'); return; }

    UI.setState('processing');
    // Vide les inputs AVANT de collecter → Mistral remplira
    UI.scoreInputs.forEach(inp => inp.value = '');
    try {
      const res = await api.saveCorrection(
        CTX.studentId, CTX.assignmentId, text, UI.collectScores()
      );
      correctionId = res.correction_id;

      // Upload audio en parallèle (non bloquant)
      if (audioBlob) api.uploadAudio(correctionId, audioBlob).catch(console.warn);

      // Poll Mistral toutes les 2 s
      pollTimer = setInterval(async () => {
        const data = await api.getStatus(correctionId).catch(() => null);
        if (!data) return;
        if (data.status === 'draft' || data.status === 'published') {
          clearInterval(pollTimer);
          UI.setState('done', data);
          // Injection des notes extraites par Mistral (GET — pas de CSRF requis)
          fetch('/teacher/api/correction/' + correctionId + '/scores')
            .then(r => r.json())
            .then(scores => {
              scores.forEach(s => {
                const inp = document.querySelector('.score-input[data-qid="' + s.question_id + '"]');
                if (inp) inp.value = s.score;
              });
            })
            .catch(console.warn);
        }
      }, 2000);

    } catch (err) {
      alert('Erreur : ' + err.message);
      UI.setState('stopped');
    }
  });

  UI.btnPublish?.addEventListener('click', async () => {
    if (!correctionId) return;
    try {
      const res = await api.publish(correctionId);
      UI.setState('published', res);
    } catch (err) {
      alert('Erreur publication : ' + err.message);
    }
  });
});