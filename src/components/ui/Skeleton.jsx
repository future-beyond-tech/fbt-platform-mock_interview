/**
 * Skeleton — shimmer placeholder used during initial loads and lazy suspense.
 * Props:
 *   shape:  'line' | 'circle' | 'rect' | 'card'
 *   width:  CSS width (string)
 *   height: CSS height (string)
 *   lines:  when shape='line', number of stacked lines
 */
export default function Skeleton({
  shape = 'line',
  width,
  height,
  lines = 1,
  className = '',
  style,
  ...rest
}) {
  if (shape === 'line' && lines > 1) {
    return (
      <div className={`t-skeleton-stack ${className}`} aria-hidden="true" {...rest}>
        {Array.from({ length: lines }).map((_, i) => (
          <span
            key={i}
            className="t-skeleton t-skeleton--line"
            style={{ width: i === lines - 1 ? '70%' : width, height }}
          />
        ))}
      </div>
    );
  }

  const classes = ['t-skeleton', `t-skeleton--${shape}`, className].filter(Boolean).join(' ');
  return (
    <span
      className={classes}
      style={{ width, height, ...style }}
      aria-hidden="true"
      {...rest}
    />
  );
}

/**
 * StartScreenSkeleton — matches the UploadPage layout to keep CLS = 0.
 * Used as the initial "Connecting..." loader fallback.
 */
export function StartScreenSkeleton() {
  return (
    <div className="t-skeleton-page" role="status" aria-live="polite" aria-label="Loading application">
      <div className="t-skeleton-hero">
        <Skeleton shape="circle" width="64px" height="64px" />
        <Skeleton shape="rect" width="260px" height="24px" />
        <Skeleton shape="rect" width="360px" height="14px" />
      </div>
      <div className="t-skeleton-dropzone">
        <Skeleton shape="circle" width="48px" height="48px" />
        <Skeleton shape="rect" width="200px" height="16px" />
        <Skeleton shape="rect" width="140px" height="12px" />
      </div>
      <Skeleton shape="rect" width="100%" height="52px" />
      <span className="t-sr-only">Loading…</span>
    </div>
  );
}

/**
 * SessionScreenSkeleton — used as Suspense fallback when lazy loading the
 * active interview screen, keeping spatial reservation stable.
 */
export function SessionScreenSkeleton() {
  return (
    <div className="t-skeleton-page" role="status" aria-live="polite" aria-label="Loading interview">
      <div className="t-skeleton-row">
        <Skeleton shape="rect" width="80px" height="32px" />
        <Skeleton shape="rect" width="140px" height="14px" />
        <Skeleton shape="rect" width="48px" height="24px" />
      </div>
      <Skeleton shape="rect" width="100%" height="8px" />
      <div className="t-skeleton-bubble">
        <Skeleton shape="circle" width="72px" height="72px" />
        <div style={{ flex: 1 }}>
          <Skeleton shape="line" lines={3} height="14px" width="100%" />
        </div>
      </div>
      <Skeleton shape="rect" width="100%" height="120px" />
      <span className="t-sr-only">Loading…</span>
    </div>
  );
}
