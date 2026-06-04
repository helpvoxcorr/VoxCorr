function initWaveform(audioUrl, containerId, correctionId) {
    const wavesurfer = WaveSurfer.create({
        container: '#' + containerId,
        waveColor: '#4F4A85',
        progressColor: '#39FF14',
        cursorColor: '#FF0000',
        barWidth: 2,
        barRadius: 3,
        height: 100,
        responsive: true,
        url: audioUrl
    });
    wavesurfer.on('ready', () => console.log('Waveform prêt'));
    window.wavesurfer = wavesurfer;
}