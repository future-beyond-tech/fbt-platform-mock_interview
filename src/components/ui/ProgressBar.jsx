/**
 * ProgressBar — determinate (with value) or indeterminate.
 * value: 0..100 (omit for indeterminate)
 * size:  'sm' | 'md' (default) | 'lg'
 * label: accessible label (string)
 */
export default function ProgressBar({
  value,
  size = 'md',
  label,
  className = '',
  ...rest
}) {
  const indeterminate = value == null || Number.isNaN(value);
  const clamped = indeterminate ? 0 : Math.max(0, Math.min(100, value));

  const classes = [
    't-progress',
    size !== 'md' && `t-progress--${size}`,
    indeterminate && 't-progress--indeterminate',
    className,
  ]
    .filter(Boolean)
    .join(' ');

  return (
    <div
      className={classes}
      role="progressbar"
      aria-label={label}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={indeterminate ? undefined : clamped}
      {...rest}
    >
      <div
        className="t-progress__fill"
        style={indeterminate ? undefined : { width: `${clamped}%` }}
      />
    </div>
  );
}
