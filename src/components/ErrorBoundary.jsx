/**
 * components/ErrorBoundary.jsx — Generic React error boundary.
 *
 * Wrap any lazy-loaded feature route with this component so a crash in one
 * section of the UI does not bring down the entire app.
 *
 * Usage:
 *   <ErrorBoundary feature="Interview Session">
 *     <InterviewSession … />
 *   </ErrorBoundary>
 *
 *   <ErrorBoundary fallback={<p>Custom fallback</p>}>
 *     <SomeComponent />
 *   </ErrorBoundary>
 */

import { Component } from 'react';

function DefaultFallback({ feature, error, onReset }) {
  return (
    <div role="alert" className="t-error-boundary">
      <h2 className="t-error-boundary__title">
        {feature ? `${feature} encountered an error` : 'Something went wrong'}
      </h2>
      <p className="t-error-boundary__message">
        {error?.message || 'An unexpected error occurred.'}
      </p>
      {onReset && (
        <button type="button" className="t-error-boundary__reset" onClick={onReset}>
          Try again
        </button>
      )}
    </div>
  );
}

export default class ErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null };
    this.handleReset = this.handleReset.bind(this);
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }

  componentDidCatch(error, info) {
    const { feature = 'Unknown' } = this.props;
    // In production you would send this to an error reporting service.
    console.error(`[ErrorBoundary:${feature}]`, error, info.componentStack);
  }

  handleReset() {
    this.setState({ hasError: false, error: null });
    this.props.onReset?.();
  }

  render() {
    const { hasError, error } = this.state;
    const { children, fallback, feature } = this.props;

    if (!hasError) return children;

    if (fallback) return typeof fallback === 'function' ? fallback({ error, onReset: this.handleReset }) : fallback;

    return (
      <DefaultFallback
        feature={feature}
        error={error}
        onReset={this.handleReset}
      />
    );
  }
}
