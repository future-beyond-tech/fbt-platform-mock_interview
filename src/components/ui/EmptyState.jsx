/**
 * EmptyState — presentation-only primitive for "no content yet" scenarios.
 * Composes cleanly with Button for action CTAs. No side effects, no fetches.
 *
 * Props:
 *   icon:    node rendered inside the icon well (emoji or <svg />)
 *   title:   short, action-oriented heading
 *   children: supporting description (prefer 1–2 sentences)
 *   actions: node (typically one or two <Button /> children)
 */
export default function EmptyState({
  icon = '\u2728',
  title,
  children,
  actions,
  className = '',
  ...rest
}) {
  const classes = ['t-empty', className].filter(Boolean).join(' ');
  return (
    <div className={classes} role="status" {...rest}>
      <span className="t-empty__icon" aria-hidden="true">{icon}</span>
      {title && <h3 className="t-empty__title">{title}</h3>}
      {children && <p className="t-empty__desc">{children}</p>}
      {actions && <div className="t-empty__actions">{actions}</div>}
    </div>
  );
}
