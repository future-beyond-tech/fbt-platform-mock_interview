/**
 * Alert — status message primitive.
 * tone: 'info' | 'success' | 'warning' | 'danger' (default 'info')
 * Uses role=alert for warning/danger (assertive), role=status otherwise.
 */
const ICONS = {
  info: 'i',
  success: '\u2713',
  warning: '!',
  danger: '\u2715',
};

export default function Alert({
  tone = 'info',
  title,
  children,
  actions,
  icon,
  className = '',
  ...rest
}) {
  const role = tone === 'warning' || tone === 'danger' ? 'alert' : 'status';
  const live = role === 'alert' ? 'assertive' : 'polite';
  const classes = ['t-alert', `t-alert--${tone}`, className].filter(Boolean).join(' ');

  return (
    <div className={classes} role={role} aria-live={live} {...rest}>
      <span className="t-alert__icon" aria-hidden="true">{icon ?? ICONS[tone]}</span>
      <div className="t-alert__body">
        {title && <div className="t-alert__title">{title}</div>}
        {children && <div className="t-alert__desc">{children}</div>}
        {actions && <div className="t-alert__actions">{actions}</div>}
      </div>
    </div>
  );
}
