/**
 * Dev-only a11y auditor.
 *
 * Loads @axe-core/react dynamically so it never enters the production bundle.
 * Silently no-ops if the package isn't installed, so Phase 3 does not force a
 * hard dependency. To enable: `npm install --save-dev @axe-core/react`.
 *
 * Violations print to the devtools console on every render pass.
 *
 * Note: the import specifier is built from a variable so Vite's static
 * import-analysis skips it. A bare literal (even with @vite-ignore) still
 * trips the analyzer in some Vite versions and hard-errors when the package
 * isn't installed — which would defeat the "optional dep" design.
 */
export async function installAxe(React, ReactDOM) {
  if (!import.meta.env.DEV) return;
  try {
    const specifier = ['@axe-core', 'react'].join('/');
    const mod = await import(/* @vite-ignore */ specifier);
    const axe = mod.default || mod;
    if (typeof axe !== 'function') return;
    // 1000 ms debounce between audits, WCAG 2.2 AA tags.
    axe(React, ReactDOM, 1000, {
      runOnly: {
        type: 'tag',
        values: ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa', 'best-practice'],
      },
    });
    console.info('[a11y] axe-core audit active');
  } catch {
    // Package not installed — skip silently. This keeps Phase 3 additive.
  }
}
