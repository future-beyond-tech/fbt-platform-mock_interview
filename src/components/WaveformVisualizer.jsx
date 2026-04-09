import { useEffect, useRef } from 'react';

/**
 * Live audio waveform visualizer shown when recording voice.
 */
export default function WaveformVisualizer({ active }) {
  const canvasRef = useRef(null);
  const rafRef = useRef(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    const w = canvas.width = 200;
    const h = canvas.height = 40;
    const bars = 24;
    const barW = 4;
    const gap = (w - bars * barW) / (bars - 1);
    let phase = 0;

    function draw() {
      ctx.clearRect(0, 0, w, h);
      phase += 0.12;

      for (let i = 0; i < bars; i++) {
        const amp = active
          ? (Math.sin(phase + i * 0.5) * 0.4 + 0.5) * h * 0.8
          : 2;
        const x = i * (barW + gap);
        const y = (h - amp) / 2;

        ctx.fillStyle = active ? `rgba(100, 255, 218, ${0.4 + Math.sin(phase + i * 0.3) * 0.3})` : 'rgba(255,255,255,0.1)';
        ctx.beginPath();
        ctx.roundRect(x, y, barW, amp, 2);
        ctx.fill();
      }

      rafRef.current = requestAnimationFrame(draw);
    }
    draw();

    return () => cancelAnimationFrame(rafRef.current);
  }, [active]);

  return <canvas ref={canvasRef} className="waveform" width={200} height={40} />;
}
