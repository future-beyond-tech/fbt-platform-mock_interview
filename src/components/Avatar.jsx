/**
 * Animated AI interviewer avatar.
 * States: idle, speaking, thinking, happy, disappointed
 */
export default function Avatar({ state = 'idle', size = 80 }) {
  const s = size;
  const cx = s / 2;
  const cy = s / 2;

  // Eye positions
  const eyeY = cy - s * 0.06;
  const eyeL = cx - s * 0.12;
  const eyeR = cx + s * 0.12;
  const eyeSize = s * 0.045;

  // Mouth
  const mouthY = cy + s * 0.12;

  const stateClass = `avatar avatar--${state}`;

  return (
    <div className={stateClass} style={{ width: s, height: s }}>
      <svg viewBox={`0 0 ${s} ${s}`} width={s} height={s}>
        {/* Glow ring */}
        <circle
          cx={cx} cy={cy} r={s * 0.46}
          fill="none"
          stroke="url(#avatarGlow)"
          strokeWidth={2}
          className="avatar-ring"
        />

        {/* Face background */}
        <circle cx={cx} cy={cy} r={s * 0.38} fill="#1a1a2e" />
        <circle cx={cx} cy={cy} r={s * 0.36} fill="#16213e" />

        {/* Eyes */}
        <circle cx={eyeL} cy={eyeY} r={eyeSize} fill="#64ffda" className="avatar-eye avatar-eye--left" />
        <circle cx={eyeR} cy={eyeY} r={eyeSize} fill="#64ffda" className="avatar-eye avatar-eye--right" />

        {/* Eye glow */}
        <circle cx={eyeL} cy={eyeY} r={eyeSize * 2.2} fill="#64ffda" opacity="0.08" />
        <circle cx={eyeR} cy={eyeY} r={eyeSize * 2.2} fill="#64ffda" opacity="0.08" />

        {/* Mouth — changes by state */}
        {state === 'speaking' && (
          <ellipse cx={cx} cy={mouthY} rx={s * 0.08} ry={s * 0.05} fill="#64ffda" className="avatar-mouth-speak" />
        )}
        {state === 'thinking' && (
          <line x1={cx - s * 0.08} y1={mouthY} x2={cx + s * 0.08} y2={mouthY} stroke="#64ffda" strokeWidth={2} strokeLinecap="round" opacity={0.5} />
        )}
        {state === 'happy' && (
          <path
            d={`M ${cx - s * 0.1} ${mouthY - s * 0.02} Q ${cx} ${mouthY + s * 0.08} ${cx + s * 0.1} ${mouthY - s * 0.02}`}
            fill="none" stroke="#64ffda" strokeWidth={2} strokeLinecap="round"
          />
        )}
        {state === 'disappointed' && (
          <path
            d={`M ${cx - s * 0.08} ${mouthY + s * 0.03} Q ${cx} ${mouthY - s * 0.04} ${cx + s * 0.08} ${mouthY + s * 0.03}`}
            fill="none" stroke="#ff6b6b" strokeWidth={2} strokeLinecap="round"
          />
        )}
        {state === 'idle' && (
          <line x1={cx - s * 0.06} y1={mouthY} x2={cx + s * 0.06} y2={mouthY} stroke="#64ffda" strokeWidth={2} strokeLinecap="round" opacity={0.6} />
        )}

        {/* Gradient defs */}
        <defs>
          <radialGradient id="avatarGlow">
            <stop offset="0%" stopColor="#64ffda" stopOpacity="0.6" />
            <stop offset="100%" stopColor="#3B82F6" stopOpacity="0.3" />
          </radialGradient>
        </defs>
      </svg>
    </div>
  );
}
