import { useState, useRef, useCallback, useEffect } from 'react';
import { transcribeAudio } from '../api';

/**
 * useVoice — Groq Whisper STT (primary) with Web Speech API fallback.
 *
 * When groqApiKey is provided:
 *   - Click Start → MediaRecorder begins capturing mic audio
 *   - Click Stop  → audio blob sent to /api/transcribe → Whisper returns text
 *   - Text is appended via onTranscript()
 *
 * When no groqApiKey:
 *   - Falls back to browser Web Speech API (real-time, lower quality)
 */

const SR = typeof window !== 'undefined'
  ? (window.SpeechRecognition || window.webkitSpeechRecognition)
  : null;

export function useVoice(onTranscript, groqApiKey = '') {
  const [isRecording, setIsRecording] = useState(false);
  const [isTranscribing, setIsTranscribing] = useState(false);
  const [hasMic, setHasMic] = useState(true);
  const [label, setLabel] = useState('Click Voice to speak your answer');
  const [error, setError] = useState('');

  const onTranscriptRef = useRef(onTranscript);
  const groqKeyRef = useRef(groqApiKey);
  const isRecRef = useRef(false);

  useEffect(() => { onTranscriptRef.current = onTranscript; }, [onTranscript]);
  useEffect(() => { groqKeyRef.current = groqApiKey; }, [groqApiKey]);

  const mediaRecorderRef = useRef(null);
  const chunksRef = useRef([]);
  const streamRef = useRef(null);
  const pendingWhisperStopRef = useRef(null);
  const appendWhisperResultRef = useRef(true);

  const recogRef = useRef(null);
  const hasMicRef = useRef(true);

  const useWhisper = () => !!groqKeyRef.current;

  useEffect(() => {
    if (!SR || recogRef.current) return;

    const recognition = new SR();
    recognition.continuous = true;
    recognition.interimResults = true;
    recognition.lang = 'en-US';

    recognition.onresult = (event) => {
      let interim = '';

      for (let i = event.resultIndex; i < event.results.length; i++) {
        if (event.results[i].isFinal) {
          onTranscriptRef.current(event.results[i][0].transcript);
        } else {
          interim = event.results[i][0].transcript;
        }
      }

      if (interim) setLabel('Hearing: ' + interim);
    };

    recognition.onerror = (event) => {
      if (event.error === 'not-allowed' || event.error === 'service-not-allowed') {
        hasMicRef.current = false;
        setHasMic(false);
        isRecRef.current = false;
        setIsRecording(false);
        setLabel('Mic access denied. Type your answer below.');
        return;
      }

      if (event.error === 'no-speech' || event.error === 'network' || event.error === 'aborted') return;

      isRecRef.current = false;
      setIsRecording(false);
      setLabel('Click Voice to speak your answer');
    };

    recognition.onend = () => {
      if (isRecRef.current && hasMicRef.current) {
        try {
          recognition.start();
        } catch {
          setTimeout(() => {
            if (isRecRef.current && hasMicRef.current) {
              try {
                recognition.start();
              } catch {
                isRecRef.current = false;
                setIsRecording(false);
                setLabel('Click Voice to speak your answer');
              }
            }
          }, 200);
        }
      } else {
        isRecRef.current = false;
        setIsRecording(false);
        setLabel('Click Voice to speak your answer');
      }
    };

    recogRef.current = recognition;
  }, []);

  const startWhisper = useCallback(async () => {
    if (pendingWhisperStopRef.current) return;

    setError('');
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;
      chunksRef.current = [];

      const mimeType = ['audio/webm;codecs=opus', 'audio/webm', 'audio/ogg'].find(
        type => MediaRecorder.isTypeSupported(type)
      ) || '';

      const mediaRecorder = new MediaRecorder(stream, mimeType ? { mimeType } : {});
      mediaRecorder.ondataavailable = (event) => {
        if (event.data.size > 0) chunksRef.current.push(event.data);
      };
      mediaRecorder.start(250);
      mediaRecorderRef.current = mediaRecorder;

      isRecRef.current = true;
      setIsRecording(true);
      setLabel('Recording... click Stop when done');
    } catch {
      setHasMic(false);
      setLabel('Mic access denied. Type your answer below.');
    }
  }, []);

  const stopWhisper = useCallback(async (appendTranscript = true) => {
    appendWhisperResultRef.current = appendTranscript;

    if (pendingWhisperStopRef.current) {
      if (!appendTranscript) setLabel('Click Voice to speak your answer');
      return pendingWhisperStopRef.current;
    }

    const mediaRecorder = mediaRecorderRef.current;
    const stream = streamRef.current;
    if (!mediaRecorder) return '';

    isRecRef.current = false;
    setIsRecording(false);
    setError('');

    if (appendTranscript) {
      setLabel('Transcribing with Whisper...');
      setIsTranscribing(true);
    } else {
      setLabel('Click Voice to speak your answer');
    }

    const stopPromise = (async () => {
      await new Promise((resolve) => {
        mediaRecorder.onstop = resolve;
        mediaRecorder.stop();
      });

      stream?.getTracks().forEach(track => track.stop());
      streamRef.current = null;
      mediaRecorderRef.current = null;

      try {
        const blob = new Blob(chunksRef.current, { type: mediaRecorder.mimeType || 'audio/webm' });
        chunksRef.current = [];

        if (!appendWhisperResultRef.current) return '';

        if (blob.size < 1000) {
          setLabel('Recording too short — try again');
          setTimeout(() => setLabel('Click Voice to speak your answer'), 3000);
          return '';
        }

        const text = await transcribeAudio(blob, groqKeyRef.current);
        if (text) {
          if (appendWhisperResultRef.current) {
            onTranscriptRef.current(text);
            setLabel(`Transcribed ${text.split(' ').length} words`);
            setTimeout(() => setLabel('Click Voice to speak your answer'), 3000);
          }
          return text;
        }

        if (appendWhisperResultRef.current) {
          setLabel('No speech detected — try again');
          setTimeout(() => setLabel('Click Voice to speak your answer'), 3000);
        }
        return '';
      } catch (eventError) {
        if (appendWhisperResultRef.current) {
          setError('Transcription failed: ' + eventError.message);
          setLabel('Click Voice to speak your answer');
        }
        return '';
      } finally {
        setIsTranscribing(false);
        pendingWhisperStopRef.current = null;
        appendWhisperResultRef.current = true;
      }
    })();

    pendingWhisperStopRef.current = stopPromise;
    return stopPromise;
  }, []);

  const startSpeech = useCallback(() => {
    if (!hasMicRef.current || !recogRef.current) return;

    isRecRef.current = true;
    try {
      recogRef.current.start();
      setIsRecording(true);
      setLabel('Listening — speak now...');
    } catch (eventError) {
      if (eventError.name === 'InvalidStateError') {
        setIsRecording(true);
        setLabel('Listening — speak now...');
      }
    }
  }, []);

  const stopSpeech = useCallback(() => {
    isRecRef.current = false;
    try { recogRef.current?.stop(); } catch { /* ignore */ }
    setIsRecording(false);
    setLabel('Click Voice to speak your answer');
  }, []);

  const toggle = useCallback(() => {
    if (!hasMic) return;

    if (isRecording) {
      useWhisper() ? void stopWhisper(true) : stopSpeech();
    } else {
      useWhisper() ? startWhisper() : startSpeech();
    }
  }, [hasMic, isRecording, startSpeech, startWhisper, stopSpeech, stopWhisper]);

  const finish = useCallback(async () => {
    if (useWhisper()) return stopWhisper(true);
    stopSpeech();
    return '';
  }, [stopSpeech, stopWhisper]);

  const cancel = useCallback(async () => {
    if (useWhisper()) return stopWhisper(false);
    stopSpeech();
    return '';
  }, [stopSpeech, stopWhisper]);

  const mode = useWhisper() ? 'whisper' : SR ? 'browser' : 'none';

  return { isRecording, isTranscribing, hasMic, label, error, mode, toggle, finish, cancel };
}
