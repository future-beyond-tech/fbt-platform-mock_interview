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
  const finalTranscriptRef = useRef('');

  // Dual-recording: in browser mode, also record audio so Whisper can rescue short results.
  const dualRecorderRef = useRef(null);
  const dualChunksRef = useRef([]);
  const dualStreamRef = useRef(null);

  const lastInterimRef = useRef('');     // track interim text so it's not lost on restart
  const restartTimerRef = useRef(null);

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
        const text = event.results[i][0].transcript;
        if (event.results[i].isFinal) {
          finalTranscriptRef.current += text + ' ';
          lastInterimRef.current = '';  // clear — it became final
          onTranscriptRef.current(text);
        } else {
          interim = text;
        }
      }

      // Save interim so we can rescue it if recognition restarts before it becomes final.
      if (interim) {
        lastInterimRef.current = interim;
        setLabel('Hearing: ' + interim);
      }
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
      // Flush any interim text that never became final — Chrome drops it on restart.
      if (lastInterimRef.current && isRecRef.current) {
        const rescued = lastInterimRef.current.trim();
        if (rescued) {
          finalTranscriptRef.current += rescued + ' ';
          onTranscriptRef.current(rescued);
        }
        lastInterimRef.current = '';
      }

      if (isRecRef.current && hasMicRef.current) {
        // Restart immediately, with a short fallback delay if it fails.
        clearTimeout(restartTimerRef.current);
        try {
          recognition.start();
        } catch {
          restartTimerRef.current = setTimeout(() => {
            if (isRecRef.current && hasMicRef.current) {
              try {
                recognition.start();
              } catch {
                isRecRef.current = false;
                setIsRecording(false);
                setLabel('Click Voice to speak your answer');
              }
            }
          }, 100);  // 100ms — minimise the gap
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

  const startSpeech = useCallback(async () => {
    if (!hasMicRef.current || !recogRef.current) return;

    finalTranscriptRef.current = '';
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

    // Start a background MediaRecorder so Whisper can rescue short/bad results.
    if (groqKeyRef.current) {
      try {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        dualStreamRef.current = stream;
        dualChunksRef.current = [];
        const mimeType = ['audio/webm;codecs=opus', 'audio/webm', 'audio/ogg'].find(
          type => MediaRecorder.isTypeSupported(type)
        ) || '';
        const recorder = new MediaRecorder(stream, mimeType ? { mimeType } : {});
        recorder.ondataavailable = (e) => {
          if (e.data.size > 0) dualChunksRef.current.push(e.data);
        };
        recorder.start(250);
        dualRecorderRef.current = recorder;
      } catch {
        // Non-fatal: Whisper rescue won't be available.
      }
    }
  }, []);

  const stopSpeech = useCallback(async () => {
    isRecRef.current = false;
    clearTimeout(restartTimerRef.current);
    lastInterimRef.current = '';
    try { recogRef.current?.stop(); } catch { /* ignore */ }
    setIsRecording(false);

    // Stop the dual recorder if running.
    const dualRecorder = dualRecorderRef.current;
    const dualStream = dualStreamRef.current;

    if (dualRecorder && dualRecorder.state !== 'inactive') {
      const browserWords = (finalTranscriptRef.current || '').trim().split(/\s+/).filter(Boolean).length;

      // If browser gave fewer than 5 words, try Whisper rescue.
      if (browserWords < 5 && groqKeyRef.current) {
        setLabel('Short result — trying Whisper...');
        setIsTranscribing(true);

        try {
          await new Promise((resolve) => {
            dualRecorder.onstop = resolve;
            dualRecorder.stop();
          });

          const blob = new Blob(dualChunksRef.current, { type: dualRecorder.mimeType || 'audio/webm' });
          dualChunksRef.current = [];

          if (blob.size > 1000) {
            const text = await transcribeAudio(blob, groqKeyRef.current);
            if (text && text.trim().split(/\s+/).length > browserWords) {
              // Whisper gave a better result — replace.
              onTranscriptRef.current(text);
              setLabel(`Whisper rescued: ${text.split(' ').length} words`);
              setTimeout(() => setLabel('Click Voice to speak your answer'), 3000);
              finalTranscriptRef.current = '';
              setIsTranscribing(false);
              dualStream?.getTracks().forEach(t => t.stop());
              dualStreamRef.current = null;
              dualRecorderRef.current = null;
              return;
            }
          }
        } catch {
          // Non-fatal: keep the browser result.
        }
        setIsTranscribing(false);
      } else {
        try { dualRecorder.stop(); } catch { /* ignore */ }
      }
    }

    // Clean up dual recording resources.
    dualStream?.getTracks().forEach(t => t.stop());
    dualStreamRef.current = null;
    dualRecorderRef.current = null;
    finalTranscriptRef.current = '';
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
