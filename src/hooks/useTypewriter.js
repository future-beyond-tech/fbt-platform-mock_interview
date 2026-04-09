import { useState, useEffect, useRef } from 'react';

export function useTypewriter(text, speed = 28) {
  const [displayed, setDisplayed] = useState('');
  const [done, setDone] = useState(false);
  const idx = useRef(0);

  useEffect(() => {
    idx.current = 0;
    setDisplayed('');
    setDone(false);

    if (!text) { setDone(true); return; }

    const timer = setInterval(() => {
      idx.current++;
      setDisplayed(text.slice(0, idx.current));
      if (idx.current >= text.length) {
        setDone(true);
        clearInterval(timer);
      }
    }, speed);

    return () => clearInterval(timer);
  }, [text, speed]);

  const skip = () => {
    setDisplayed(text);
    setDone(true);
  };

  return { displayed, done, skip };
}
