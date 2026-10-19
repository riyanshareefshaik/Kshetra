// Voice in/out. Browser speech first (free, on-device or browser-provided); server fallbacks
// (Bhashini / Whisper for input, gTTS for output) through the Kshetra API.
import { api } from "../api.js";

const LOCALE = { te: "te-IN", hi: "hi-IN", en: "en-IN" };

export function browserRecognition() {
  return window.SpeechRecognition || window.webkitSpeechRecognition || null;
}

/** Listen once with the browser recogniser. Resolves to the transcript. */
export function listenOnce(lang) {
  const Rec = browserRecognition();
  if (!Rec) return Promise.reject(new Error("no browser speech recognition"));
  return new Promise((resolve, reject) => {
    const rec = new Rec();
    rec.lang = LOCALE[lang] || "en-IN";
    rec.interimResults = false;
    rec.maxAlternatives = 1;
    rec.onresult = (e) => resolve(e.results[0][0].transcript);
    rec.onerror = (e) => reject(new Error(e.error || "speech error"));
    rec.onnomatch = () => reject(new Error("did not catch that"));
    rec.start();
  });
}

/** Record audio with the microphone until stop() is called. */
export async function startRecording() {
  const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
  const recorder = new MediaRecorder(stream);
  const chunks = [];
  recorder.ondataavailable = (e) => chunks.push(e.data);
  recorder.start();
  return {
    stop: () => new Promise((resolve) => {
      recorder.onstop = () => {
        stream.getTracks().forEach((tr) => tr.stop());
        resolve(new Blob(chunks, { type: recorder.mimeType || "audio/webm" }));
      };
      recorder.stop();
    }),
  };
}

export async function speak(text, lang) {
  const synth = window.speechSynthesis;
  const voice = synth?.getVoices().find((v) => v.lang?.toLowerCase().startsWith(lang));
  if (synth && (voice || lang === "en")) {
    synth.cancel();
    const u = new SpeechSynthesisUtterance(text);
    u.lang = LOCALE[lang];
    if (voice) u.voice = voice;
    synth.speak(u);
    return;
  }
  const blob = await api.speak(text, lang);         // server fallback (gTTS)
  const audio = new Audio(URL.createObjectURL(blob));
  await audio.play();
}
