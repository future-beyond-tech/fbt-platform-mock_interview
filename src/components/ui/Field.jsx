import { useId } from 'react';

/**
 * Field — label + control + help/error wrapper.
 * Props:
 *   label:       visible label text
 *   help:        helper text (rendered if no error)
 *   error:       error message (overrides help, sets aria-invalid)
 *   required:    marks label with required glyph
 *   as:          'input' | 'textarea' | 'select' (default 'input')
 *   children:    when provided, renders custom control; id/aria are wired via renderProp
 */
export default function Field({
  label,
  help,
  error,
  required = false,
  as = 'input',
  id: idProp,
  className = '',
  children,
  ...controlProps
}) {
  const autoId = useId();
  const id = idProp || autoId;
  const describedBy = error ? `${id}-err` : help ? `${id}-help` : undefined;

  const wrapperClasses = [
    't-field',
    error && 't-field--invalid',
    className,
  ]
    .filter(Boolean)
    .join(' ');

  const controlCommon = {
    id,
    'aria-invalid': error ? true : undefined,
    'aria-describedby': describedBy,
    'aria-required': required || undefined,
    className: 't-field__control',
    ...controlProps,
  };

  let control;
  if (typeof children === 'function') {
    control = children(controlCommon);
  } else if (children) {
    control = children;
  } else if (as === 'textarea') {
    control = <textarea {...controlCommon} />;
  } else if (as === 'select') {
    control = <select {...controlCommon} />;
  } else {
    control = <input {...controlCommon} />;
  }

  return (
    <div className={wrapperClasses}>
      {label && (
        <label className="t-field__label" htmlFor={id}>
          {label}
          {required && <span className="t-field__required" aria-hidden="true">*</span>}
        </label>
      )}
      {control}
      {error ? (
        <p id={`${id}-err`} className="t-field__error" role="alert">
          {error}
        </p>
      ) : help ? (
        <p id={`${id}-help`} className="t-field__help">
          {help}
        </p>
      ) : null}
    </div>
  );
}
