/**
 * Badge — compact status pill.
 * tone: 'default' | 'accent' | 'success' | 'warning' | 'danger' | 'info'
 */
import './ui.css';

export default function Badge({ tone = 'default', className = '', children, ...rest }) {
  const classes = [
    't-badge',
    tone !== 'default' && `t-badge--${tone}`,
    className,
  ]
    .filter(Boolean)
    .join(' ');
  return (
    <span className={classes} {...rest}>
      {children}
    </span>
  );
}
