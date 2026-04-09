import { useEffect, useState } from 'react';

/**
 * LaunchLoader — cinematic boot animation shown while the app warms up.
 *
 * Not your typical spinner. A pulsing "neural core" sits inside three tilted
 * orbit rings, each carrying a tiny node that sweeps around it. Six ambient
 * particles drift through the backdrop, and a rotating status caption cycles
 * through human-feeling phrases so the wait reads as intentional, not idle.
 *
 * Fully accessible: a single aria-live region announces the current phase to
 * assistive tech (not the decorative orbit layers). prefers-reduced-motion
 * collapses all movement down to a gentle glow pulse.
 */

const PHASES = [
  { key: 'ignite',    label: 'Waking the interviewer' },
  { key: 'calibrate', label: 'Calibrating tone & pace' },
  { key: 'sharpen',   label: 'Sharpening questions' },
  { key: 'align',     label: 'Aligning to your profile' },
  { key: 'ready',     label: 'Almost ready' },
];

export default function LaunchLoader({ label = 'Loading' }) {
  const [phaseIdx, setPhaseIdx] = useState(0);

  useEffect(() => {
    const reduced = typeof window !== 'undefined'
      && window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
    if (reduced) return undefined;
    const id = window.setInterval(() => {
      setPhaseIdx((i) => (i + 1) % PHASES.length);
    }, 1600);
    return () => window.clearInterval(id);
  }, []);

  const phase = PHASES[phaseIdx];

  return (
    <div
      className="launch-loader"
      role="status"
      aria-live="polite"
      aria-label={label}
    >
      {/* Ambient drifting particles */}
      <div className="launch-loader__field" aria-hidden="true">
        {Array.from({ length: 6 }).map((_, i) => (
          <span key={i} className={`launch-loader__mote launch-loader__mote--${i + 1}`} />
        ))}
      </div>

      {/* Core + orbits */}
      <div className="launch-loader__stage" aria-hidden="true">
        <div className="launch-loader__halo" />
        <div className="launch-loader__core">
          <span className="launch-loader__core-ring" />
          <span className="launch-loader__core-ring launch-loader__core-ring--delay" />
          <span className="launch-loader__core-glyph">AI</span>
        </div>

        <div className="launch-loader__orbit launch-loader__orbit--a">
          <span className="launch-loader__node" />
        </div>
        <div className="launch-loader__orbit launch-loader__orbit--b">
          <span className="launch-loader__node" />
        </div>
        <div className="launch-loader__orbit launch-loader__orbit--c">
          <span className="launch-loader__node" />
        </div>
      </div>

      {/* Status + progress bead */}
      <div className="launch-loader__status">
        <div className="launch-loader__phases">
          {PHASES.map((p, i) => (
            <span
              key={p.key}
              className={
                'launch-loader__phase'
                + (i === phaseIdx ? ' launch-loader__phase--active' : '')
              }
              aria-hidden={i !== phaseIdx}
            >
              {p.label}
            </span>
          ))}
        </div>
        <div className="launch-loader__track" aria-hidden="true">
          <span className="launch-loader__bead" />
        </div>
        <p className="launch-loader__tagline">
          Building a thoughtful interview tailored to you
        </p>
      </div>

      {/* Screen-reader only text that updates as phases advance */}
      <span className="t-sr-only">{`${label}: ${phase.label}`}</span>
    </div>
  );
}
