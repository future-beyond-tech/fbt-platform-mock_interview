/**
 * Card — content container primitive.
 * Props:
 *   variant: 'default' | 'glass' | 'flat'
 *   interactive: boolean (adds hover affordance + role/tabIndex)
 *   title, subtitle, footer: optional slots
 */
export default function Card({
  variant = 'default',
  interactive = false,
  title,
  subtitle,
  footer,
  className = '',
  children,
  as = 'section',
  ...rest
}) {
  const Tag = as;
  const classes = [
    't-card',
    variant !== 'default' && `t-card--${variant}`,
    interactive && 't-card--interactive',
    className,
  ]
    .filter(Boolean)
    .join(' ');

  const interactiveProps = interactive
    ? { role: rest.role || 'button', tabIndex: rest.tabIndex ?? 0 }
    : {};

  return (
    <Tag className={classes} {...interactiveProps} {...rest}>
      {(title || subtitle) && (
        <header className="t-card__header">
          {title && <h3 className="t-card__title">{title}</h3>}
          {subtitle && <p className="t-card__subtitle">{subtitle}</p>}
        </header>
      )}
      <div className="t-card__body">{children}</div>
      {footer && <footer className="t-card__footer">{footer}</footer>}
    </Tag>
  );
}
