/**
 * VoxCorr — record_page.js
 * Orchestre la page de correction : dictée → analyse → vérification → publication → élève suivant.
 * window.VC est injecté par record.html.
 */
import { UI }  from './modules/ui.js?v=3';
import { api } from './modules/api.js?v=3';

const CTX = window.VC || {};
const dialog = () => window.VoxModal;

let recorder     = null;
let audioBlob    = null;
let correctionId = CTX.correctionId || null;
let pollTimer    = null;
let scoreTimer   = null;
let unsaved      = false;   // dictée non encore envoyée au serveur

function goTo(studentId) {
  if (studentId) window.location.href = `${CTX.recordBaseUrl}/${studentId}/${CTX.assignmentId}`;
}

/** Enregistre automatiquement les notes corrigées à la main. */
function scheduleScoreSave() {
  clearTimeout(scoreTimer);
  scoreTimer = setTimeout(async () => {
    const scores = UI.collectManual();
    if (!correctionId || !scores.length) return;
    try {
      const res = await api.updateScores(correctionId, scores);
      if (UI.totalScore && res.total_score != null) UI.totalScore.textContent = Number(res.total_score).toFixed(1);
      UI.clearManualFlags();
    } catch (err) {
      dialog().alert({ type: 'danger', title: 'Note non enregistrée', body: err.message });
    }
  }, 600);
}

/** Interroge le serveur jusqu'à la fin de l'analyse. */
function startPolling() {
  clearInterval(pollTimer);
  let ticks = 0;
  pollTimer = setInterval(async () => {
    ticks += 1;
    if (ticks > 90) {   // 3 minutes
      clearInterval(pollTimer);
      UI.setState('stopped');
      dialog().alert({
        type: 'warning',
        title: "L'analyse est longue",
        body: "Rechargez la page dans un instant. Si la correction est toujours « en analyse », ouvrez sa fiche et utilisez « Regénérer la synthèse et les notes »."
      });
      return;
    }
    const data = await api.getStatus(correctionId).catch(() => null);
    if (!data) return;
    if (data.status === 'draft' || data.status === 'published') {
      clearInterval(pollTimer);
      UI.setState('done', data);
      try {
        const scores = await api.getScores(correctionId);
        scores.forEach(s => {
          const inp = document.querySelector(`.score-input[data-qid="${s.question_id}"]`);
          if (inp) inp.value = s.score;
        });
      } catch (e) { console.warn(e); }
    }
  }, 2000);
}

/** Problème qui mérite une confirmation avant publication, ou null. */
function publishIssue() {
  const synth = UI.synthText?.textContent || '';
  if (synth.includes('synthèse IA indisponible')) {
    return "La synthèse IA a échoué : le texte affiché est votre dictée brute et les notes n'ont peut-être pas été extraites.";
  }
  const values = UI.scoreInputs.map(i => parseFloat(i.value) || 0);
  if (values.length && values.every(v => v === 0)) return 'Toutes les notes sont à 0.';
  return null;
}

document.addEventListener('DOMContentLoaded', () => {
  recorder = new window.VoxRecorder({
    onTranscript: (final, interim) => {
      if (UI.transcript) UI.transcript.value = final;
      if (UI.interim)    UI.interim.textContent = interim;
      unsaved = true;
    },
    onAudioReady:  (blob) => { audioBlob = blob; UI.setState('stopped'); },
    onStateChange: (state) => { if (state === 'recording') UI.setState('recording'); },
  });

  UI.setState('idle');
  if (CTX.correctionStatus === 'draft') UI.show(UI.btnPublish);
  if (CTX.correctionStatus === 'processing' && correctionId) { UI.setState('processing'); startPolling(); }

  UI.btnStart?.addEventListener('click', () => recorder.start(UI.waveformBars));
  UI.btnStop?.addEventListener('click',  () => recorder.stop(UI.waveformBars));
  UI.transcript?.addEventListener('input', () => { unsaved = true; });

  // Notes corrigées à la main : repérées, puis enregistrées automatiquement
  UI.scoreInputs.forEach(inp => inp.addEventListener('input', () => {
    inp.dataset.manual = '1';
    scheduleScoreSave();
  }));

  // Évite de perdre une dictée en quittant la page par erreur
  window.addEventListener('beforeunload', (e) => {
    if (unsaved) { e.preventDefault(); e.returnValue = ''; }
  });

  UI.btnSave?.addEventListener('click', async () => {
    const text = UI.transcript?.value?.trim() || '';
    if (!text) {
      dialog().alert({ type: 'warning', title: 'Transcription vide', body: "Dictez ou tapez votre correction avant de l'analyser." });
      return;
    }

    const manual = UI.collectManual();   // lues AVANT d'être vidées
    UI.setState('processing');
    UI.clearScores();

    const correctionData = {
      student_id: CTX.studentId, assignment_id: CTX.assignmentId, transcript: text, scores: manual,
    };

    if (!navigator.onLine) {
      await window.saveCorrectionOffline(correctionData, audioBlob);
      unsaved = false;
      dialog().alert({ type: 'info', title: 'Pas de connexion', body: 'La correction sera envoyée automatiquement quand Internet reviendra.' });
      UI.setState('idle');
      return;
    }

    try {
      const res = await api.saveCorrection(CTX.studentId, CTX.assignmentId, text, manual);
      correctionId = res.correction_id;
      unsaved = false;

      if (audioBlob) {
        api.uploadAudio(correctionId, audioBlob).catch(() => dialog().alert({
          type: 'warning',
          title: 'Audio non enregistré',
          body: "La correction est enregistrée, mais l'audio n'a pas pu être envoyé : l'élève verra « Aucun audio ». Refaites la dictée pour l'ajouter."
        }));
      }
      startPolling();
    } catch (err) {
      dialog().alert({ type: 'danger', title: 'Analyse impossible', body: err.message });
      UI.setState('stopped');
    }
  });

  UI.btnPublish?.addEventListener('click', async () => {
    if (!correctionId) return;
    const issue = publishIssue();
    if (issue) {
      const ok = await dialog().confirm({
        type: 'warning',
        title: 'Publier quand même ?',
        body: issue + '\nVous pouvez corriger les notes à la main ou refaire la dictée.',
        confirmText: 'Publier quand même'
      });
      if (!ok) return;
    }
    UI.btnPublish.disabled = true;
    try {
      const res = await api.publish(correctionId);
      UI.setState('published', res);
      document.getElementById('btn-dl-qr')?.setAttribute('href', `/teacher/correction/${correctionId}/qr.png`);
      document.getElementById('btn-next-todo')?.focus();   // Entrée = élève suivant
    } catch (err) {
      dialog().alert({ type: 'danger', title: 'Publication impossible', body: err.message });
      UI.btnPublish.disabled = false;
    }
  });

  UI.btnEditSynth?.addEventListener('click', () => {
    if (!correctionId) return;
    window.SynthEditor.open(correctionId, (html) => { if (UI.synthText) UI.synthText.innerHTML = html; });
  });
  document.getElementById('btn-next-todo')?.addEventListener('click', () => goTo(CTX.nextTodoId));
});