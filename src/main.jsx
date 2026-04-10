import React, { StrictMode } from 'react'
import ReactDOM, { createRoot } from 'react-dom/client'
import { Provider } from 'react-redux'
import { store } from './store'
import './index.css'
import App from './App.jsx'
import { installAxe } from './devtools/axe.js'

// Dev-only a11y audit — no-op in production, no-op if not installed.
if (import.meta.env.DEV) {
  void installAxe(React, ReactDOM)
}

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <Provider store={store}>
      <App />
    </Provider>
  </StrictMode>,
)
