const params = new URLSearchParams(window.location.search);
const sessionId = params.get('session_id');
const openingText = params.get('opening_text');
const apiKey = localStorage.getItem('sarvam_api_key') || '';

if (sessionId) localStorage.setItem('intervo_session', sessionId);
const activeSession = localStorage.getItem('intervo_session');

if (!activeSession) window.location.href = '/';

const orb = document.getElementById('orb');
const statusDot = document.getElementById('statusDot');
const statusText = document.getElementById('statusText');
const transcriptBox = document.getElementById('transcriptBox');
const micHint = document.getElementById('micHint');
const endBtn = document.getElementById('endBtn');

let mediaRecorder = null;
let audioChunks = [];
let isRecording = false;
let isSpeaking = false;
let interviewDone = false;
let stream = null;

function setStatus(text, type) {
  statusText.textContent = text;
  statusDot.className = 'status-dot ' + (type || '');
}

function addTranscript(text, role) {
  const empty = document.getElementById('transcriptEmpty');
  if (empty) empty.remove();
  const line = document.createElement('div');
  line.className = 'transcript-line ' + role;
  line.textContent = text;
  transcriptBox.appendChild(line);
  transcriptBox.scrollTop = transcriptBox.scrollHeight;
}

async function playAudio(url) {
  return new Promise(async (resolve) => {
    try {
      const res = await fetch(url, { headers: { 'X-Sarvam-Key': apiKey } });
      if (!res.ok) { orb.className = 'orb idle'; resolve(); return; }
      const blob = await res.blob();
      const objectUrl = URL.createObjectURL(blob);
      const audio = new Audio(objectUrl);
      orb.className = 'orb speaking';
      setStatus('Speaking', 'active');
      audio.onended = () => { orb.className = 'orb idle'; URL.revokeObjectURL(objectUrl); resolve(); };
      audio.onerror = () => { orb.className = 'orb idle'; resolve(); };
      audio.play().catch(() => { orb.className = 'orb idle'; resolve(); });
    } catch (e) {
      orb.className = 'orb idle';
      resolve();
    }
  });
}

function getMimeType() {
  const types = ['audio/mp4', 'audio/webm;codecs=opus', 'audio/webm', 'audio/ogg'];
  for (const type of types) {
    if (MediaRecorder.isTypeSupported(type)) return type;
  }
  return '';
}

async function startRecording() {
  if (isRecording || isSpeaking || interviewDone) return;
  try {
    if (!stream) {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    }
    audioChunks = [];
    const mimeType = getMimeType();
    mediaRecorder = mimeType ? new MediaRecorder(stream, { mimeType }) : new MediaRecorder(stream);
    mediaRecorder.ondataavailable = e => { if (e.data.size > 0) audioChunks.push(e.data); };
    mediaRecorder.start();
    isRecording = true;
    orb.className = 'orb recording';
    setStatus('Recording', 'recording');
    micHint.textContent = 'Release to send';
  } catch (e) {
    console.error('Mic error:', e);
    setStatus('Mic error', '');
    micHint.textContent = 'Microphone access denied. Check Safari settings.';
  }
}

async function stopRecording() {
  if (!isRecording || !mediaRecorder) return;
  isRecording = false;

  return new Promise((resolve) => {
    mediaRecorder.onstop = async () => {
      const mimeType = mediaRecorder.mimeType || 'audio/mp4';
      const blob = new Blob(audioChunks, { type: mimeType });
      await sendAudio(blob, mimeType);
      resolve();
    };
    mediaRecorder.stop();
  });
}

async function sendAudio(blob, mimeType) {
  setStatus('Processing', 'active');
  orb.className = 'orb idle';

  const ext = mimeType.includes('mp4') ? 'mp4' : mimeType.includes('ogg') ? 'ogg' : 'webm';

  const form = new FormData();
  form.append('session_id', activeSession);
  form.append('audio', blob, `audio.${ext}`);

  try {
    const res = await fetch('/api/turn', {
      method: 'POST',
      headers: { 'X-Sarvam-Key': apiKey },
      body: form,
    });
    const data = await res.json();

    if (data.user_text) addTranscript(data.user_text, 'user');
    if (data.ai_text) addTranscript(data.ai_text, 'ai');

    if (!data.ai_text) {
      setStatus('Your turn', 'active');
      micHint.textContent = 'Hold spacebar or tap orb to speak';
      return;
    }

    const audioUrl = `/api/turn-audio/${activeSession}?text=${encodeURIComponent(data.ai_text)}`;
    isSpeaking = true;
    await playAudio(audioUrl);
    isSpeaking = false;

    if (data.done) {
      interviewDone = true;
      setStatus('Interview Complete', '');
      micHint.textContent = 'Interview ended. Redirecting...';
      orb.className = 'orb idle';
      console.log('Redirecting with session:', activeSession);
      setTimeout(() => {
        window.location.href = '/feedback?session_id=' + activeSession;
      }, 2500);
    } else {
      setStatus('Your turn', 'active');
      micHint.textContent = 'Hold spacebar or tap orb to speak';
    }
  } catch (e) {
    console.error('Send error:', e);
    setStatus('Error', '');
    micHint.textContent = 'Something went wrong. Try again.';
  }
}

async function init() {
  setStatus('Loading', 'active');
  micHint.textContent = 'Preparing your interview...';
  addTranscript(openingText, 'ai');
  const audioUrl = `/api/opening-audio/${activeSession}`;
  isSpeaking = true;
  await playAudio(audioUrl);
  isSpeaking = false;
  setStatus('Your turn', 'active');
  micHint.textContent = 'Hold spacebar or tap orb to speak';
}

orb.addEventListener('mousedown', startRecording);
orb.addEventListener('mouseup', stopRecording);
orb.addEventListener('touchstart', e => { e.preventDefault(); startRecording(); });
orb.addEventListener('touchend', e => { e.preventDefault(); stopRecording(); });

document.addEventListener('keydown', e => {
  if (e.code === 'Space' && !e.repeat) { e.preventDefault(); startRecording(); }
});

document.addEventListener('keyup', e => {
  if (e.code === 'Space') { e.preventDefault(); stopRecording(); }
});

endBtn.addEventListener('click', () => {
  if (confirm('End the interview now?')) {
    console.log('Manual end with session:', activeSession);
    window.location.href = '/feedback?session_id=' + activeSession;
  }
});

async function start() {
  stream = await navigator.mediaDevices.getUserMedia({ audio: true }).catch(() => null);
  await init();
}

start();