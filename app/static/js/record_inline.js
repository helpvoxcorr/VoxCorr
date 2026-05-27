const CTX = window.VC || {};
let audioBlob = null, correctionId = CTX.correctionId || null, pollTimer = null;
const el = id => document.getElementById(id);
const show = id => { const e=el(id); if(e) e.classList.remove('d-none'); };
const hide = id => { const e=el(id); if(e) e.classList.add('d-none'); };
const bars = () => [...document.querySelectorAll('.vox-waveform-bar')];

const recorder = new VoxRecorder({
  onTranscript: (f,i) => { el('transcription').value=f; el('interim').textContent=i; },
  onAudioReady: (blob) => { audioBlob=blob; show('btn-save'); el('recording-status').textContent='Prêt à valider.'; el('action-bar')?.classList.remove('d-none'); },
  onStateChange: (s) => { if(s==='recording'){ hide('btn-start'); show('btn-stop'); hide('btn-save'); el('recording-status').textContent='⬤ En cours…'; } if(s==='stopped'){ show('btn-start'); hide('btn-stop'); } }
});

el('btn-start').onclick = () => recorder.start(bars());
el('btn-stop').onclick  = () => recorder.stop(bars());

el('btn-save').onclick = async () => {
  const text = el('transcription').value.trim();
  if(!text){ alert('Transcription vide.'); return; }
  const scores = [...document.querySelectorAll('.score-input')].map(i=>({question_id:+i.dataset.qid,score:+i.value||0})).filter(s=>s.score>0);
  hide('btn-save'); el('recording-status').textContent='Analyse Mistral…';
  const res = await fetch('/teacher/api/correction/save',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({student_id:CTX.studentId,assignment_id:CTX.assignmentId,transcript:text,scores})}).then(r=>r.json());
  correctionId = res.correction_id;
  if(audioBlob){ const fd=new FormData(); fd.append('audio',audioBlob,'c.webm'); fetch('/teacher/api/correction/'+correctionId+'/audio',{method:'POST',body:fd}).catch(()=>{}); }
  pollTimer = setInterval(async()=>{
    const d=await fetch('/teacher/api/correction/'+correctionId+'/status').then(r=>r.json()).catch(()=>null);
    if(!d||d.status==='processing') return;
    clearInterval(pollTimer);
    // ── AJOUTE ICI ──
    fetch('/teacher/api/correction/'+correctionId+'/scores')
      .then(r=>r.json()).then(scores=>{
        scores.forEach(s=>{
          const inp=document.querySelector('.score-input[data-qid="'+s.question_id+'"]');
          if(inp) inp.value=s.score;
        });
      });
    // ── FIN AJOUT ──
    show('btn-publish');
    el('recording-status').textContent='✓ Analysé';
    if(d.structured_text){ show('ai-result-section'); el('ai-formatted-text').innerHTML=d.structured_text; }
    if(d.total_score!=null) el('total-score').textContent=d.total_score;
  },2000);
};

el('btn-publish').onclick = async () => {
  const res=await fetch('/teacher/api/correction/'+correctionId+'/publish',{method:'POST'}).then(r=>r.json());
  hide('btn-publish'); show('qr-panel');
  el('qr-img').src=res.qr; el('qr-url').href=el('qr-url').textContent=res.url;
  const dlBtn=document.getElementById('btn-dl-qr'); if(dlBtn) dlBtn.href='/teacher/correction/'+correctionId+'/qr.png';
  el('recording-status').textContent='✓ Publié';
};
