class VoxRecorder {
  constructor(opts={}) {
    this.onTranscript  = opts.onTranscript  || (()=>{});
    this.onAudioReady  = opts.onAudioReady  || (()=>{});
    this.onStateChange = opts.onStateChange || (()=>{});
    this.isRecording=false; this.recognition=null; this.mediaRec=null;
    this.audioChunks=[]; this.stream=null; this.analyser=null;
    this.animFrame=null; this.transcript="";
  }
  _initRecognition() {
    const SR = window.SpeechRecognition||window.webkitSpeechRecognition;
    if (!SR) {
      console.warn('Web Speech API non disponible sur ce navigateur.');
      return null;
    }
    const r=new SR(); r.lang="fr-FR"; r.continuous=true; r.interimResults=true;
    r.onresult=(e)=>{ let interim=""; for(let i=e.resultIndex;i<e.results.length;i++){ const t=e.results[i][0].transcript; if(e.results[i].isFinal) this.transcript+=t+" "; else interim=t; } this.onTranscript(this.transcript,interim); };
    r.onerror=(e)=>console.warn(e.error);
    r.onend=()=>{ if(this.isRecording){ setTimeout(()=>{ try{r.start();}catch(_){} },200); } };
    return r;
  }
  _startWaveform(bars) {
    const data=new Uint8Array(this.analyser.frequencyBinCount);
    const draw=()=>{ this.analyser.getByteFrequencyData(data); const step=Math.floor(data.length/bars.length); bars.forEach((b,i)=>{ const v=data[i*step]||0; b.style.height=Math.max(4,(v/255)*52)+"px"; b.style.opacity=0.4+(v/255)*0.6; }); this.animFrame=requestAnimationFrame(draw); };
    draw();
  }
  _stopWaveform(bars) { if(this.animFrame) cancelAnimationFrame(this.animFrame); if(bars) bars.forEach(b=>{b.style.height="6px";b.style.opacity=".4";}); }
  async start(bars=[]) {
    if(this.isRecording) return;
    try { this.stream=await navigator.mediaDevices.getUserMedia({audio:true}); } catch(e){ window.voxShowError?.("Micro inaccessible", "Vérifiez que votre microphone est bien branché et autorisé dans les paramètres du navigateur."); return; }
    const ctx=new AudioContext(); const src=ctx.createMediaStreamSource(this.stream);
    this.analyser=ctx.createAnalyser(); this.analyser.fftSize=256; src.connect(this.analyser);
    this._startWaveform(bars);
    const mime=MediaRecorder.isTypeSupported("audio/webm;codecs=opus")?"audio/webm;codecs=opus":"audio/webm";
    this.mediaRec=new MediaRecorder(this.stream,{mimeType:mime}); this.audioChunks=[];
    this.mediaRec.ondataavailable=e=>{ if(e.data.size>0) this.audioChunks.push(e.data); };
    this.mediaRec.onstop=()=>{ this.onAudioReady(new Blob(this.audioChunks,{type:mime})); };
    this.mediaRec.start(200);
    this.recognition=this._initRecognition(); this.transcript="";
    if(this.recognition) this.recognition.start();
    this.isRecording=true; this.onStateChange("recording");
  }
  stop(bars=[]) {
    this.isRecording=false;
    if(this.recognition){try{this.recognition.stop();}catch(_){}}
    if(this.mediaRec&&this.mediaRec.state!=="inactive") this.mediaRec.stop();
    if(this.stream) this.stream.getTracks().forEach(t=>t.stop());
    this._stopWaveform(bars); this.onStateChange("stopped");
  }
}
window.VoxRecorder=VoxRecorder;