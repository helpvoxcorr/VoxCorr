/**
 * VoxCorr — module api.js
 * Tous les appels fetch centralisés ici.
 * Aucun fetch() ailleurs dans le code.
 */

async function _post(url, body, isFormData = false) {
  const res = await fetch(url, {
    method:  'POST',
    headers: isFormData ? {} : { 'Content-Type': 'application/json' },
    body:    isFormData ? body : JSON.stringify(body),
  });
  const json = await res.json().catch(() => ({ error: res.statusText }));
  if (!res.ok) throw new Error(json.error || `Erreur ${res.status}`);
  return json;
}

async function _get(url) {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`Erreur ${res.status}`);
  return res.json();
}

export const api = {
  saveCorrection(studentId, assignmentId, transcript, scores = []) {
    return _post('/teacher/api/correction/save', {
      student_id: studentId, assignment_id: assignmentId, transcript, scores,
    });
  },
  getStatus(correctionId) {
    return _get(`/teacher/api/correction/${correctionId}/status`);
  },
  uploadAudio(correctionId, blob) {
    const fd = new FormData();
    fd.append('audio', blob, 'correction.webm');
    return _post(`/teacher/api/correction/${correctionId}/audio`, fd, true);
  },
  publish(correctionId) {
    return _post(`/teacher/api/correction/${correctionId}/publish`, {});
  },
};
