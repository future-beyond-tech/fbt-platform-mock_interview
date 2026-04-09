import { forwardRef } from 'react';

/**
 * Button — primitive CTA.
 * Variants: primary | secondary | ghost | danger
 * Sizes:    sm | md (default) | lg
 *
 * A11y:
 * - Always renders a native <button> (or anchor via `as="a"`).
 * - `disabled` uses aria-disabled to preserve focusability when false.
 * - Icon-only buttons must receive `aria-label`.
 */
const Button = forwardRef(function Button(
  {
    as: Tag = 'button',
    variant = 'secondary',
    size = 'md',
    block = false,
    iconOnly = false,
    className = '',
    type,
    children,
    ...rest
  },
  ref,
) {
  const classes = [
    't-btn',
    `t-btn--${variant}`,
    size !== 'md' && `t-btn--${size}`,
    block && 't-btn--block',
    iconOnly && 't-btn--icon',
    className,
  ]
    .filter(Boolean)
    .join(' ');

  const resolvedType = Tag === 'button' ? type || 'button' : type;

  return (
    <Tag ref={ref} className={classes} type={resolvedType} {...rest}>
      {children}
    </Tag>
  );
});

export default Button;
