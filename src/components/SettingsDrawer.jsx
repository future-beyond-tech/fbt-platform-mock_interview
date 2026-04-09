import { useState, useEffect } from 'react';

export default function SettingsDrawer({ open, onClose, settings, onUpdate, providers }) {
  const [local, setLocal] = useState({ ...settings });
  const [showKey, setShowKey] = useState(false);

  useEffect(() => {
    if (open) {
      setLocal({ ...settings });
      setShowKey(false);
    }
  }, [open, settings]);

  useEffect(() => {
    if (!open) return undefined;

    const onKeyDown = (event) => {
      if (event.key === 'Escape') onClose();
    };

    document.addEventListener('keydown', onKeyDown);
    return () => document.removeEventListener('keydown', onKeyDown);
  }, [open, onClose]);

  const currentProvider = providers.find(p => p.id === local.provider);

  const handleSave = () => {
    onUpdate(local);
    onClose();
  };

  const updateActiveProfile = (patch) => {
    setLocal(prev => ({
      ...prev,
      ...patch,
      profiles: {
        ...prev.profiles,
        [prev.provider]: {
          ...(prev.profiles?.[prev.provider] || {}),
          ...patch,
        },
      },
    }));
  };

  const handleProviderSwitch = (providerId) => {
    const profile = local.profiles?.[providerId] || { apiKey: '', model: '' };
    setLocal(prev => ({
      ...prev,
      provider: providerId,
      apiKey: profile.apiKey || '',
      model: profile.model || '',
    }));
    setShowKey(false);
  };

  if (!open) return null;

  return (
    <div className="drawer-overlay" onClick={onClose}>
      <div
        className="drawer"
        onClick={e => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-labelledby="settings-title"
      >
        <div className="drawer-header">
          <h2 className="drawer-title" id="settings-title">Settings</h2>
          <button className="drawer-close" type="button" onClick={onClose} aria-label="Close settings">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
          </button>
        </div>

        <div className="drawer-body">
          {/* Provider selection */}
          <label className="field-label">LLM Provider</label>
          <div className="provider-grid">
            {providers.map(p => (
              <button
                key={p.id}
                type="button"
                className={`provider-card${local.provider === p.id ? ' active' : ''}`}
                onClick={() => handleProviderSwitch(p.id)}
              >
                <span className="provider-icon">{providerIcon(p.id)}</span>
                <span className="provider-name">{p.name}</span>
                {p.server_key_available && <span className="provider-badge">Server key</span>}
                {!p.needs_key && <span className="provider-badge">Free</span>}
              </button>
            ))}
          </div>

          {/* API key */}
          {currentProvider?.needs_key && (
            <>
              <label className="field-label">{currentProvider.name} API Key</label>
              <div className="key-input-wrap">
                <input
                  type={showKey ? 'text' : 'password'}
                  className="field-input"
                  placeholder={`Paste your ${currentProvider.name} API key...`}
                  value={local.apiKey}
                  onChange={e => updateActiveProfile({ apiKey: e.target.value })}
                  autoComplete="off"
                />
                <button
                  type="button"
                  className="key-toggle"
                  onClick={() => setShowKey(v => !v)}
                  title={showKey ? 'Hide key' : 'Show key'}
                >
                  {showKey ? '🙈' : '👁️'}
                </button>
              </div>
              {local.provider === 'groq' && (
                <p className="field-hint groq-hint">
                  Free tier — 1,000 requests/day. Get your key at{' '}
                  <a href="https://console.groq.com" target="_blank" rel="noreferrer">console.groq.com</a>
                </p>
              )}
              {currentProvider?.server_key_available && !local.apiKey && (
                <p className="field-hint">
                  A backend env key is available for this provider. Leave this blank to use it, or paste a key here to override it locally.
                </p>
              )}
              <p className="field-hint">
                Stored locally in your browser and sent only to your configured backend when a provider request is made.
              </p>
            </>
          )}

          {/* Model selection */}
          {currentProvider && (
            <>
              <label className="field-label">Model</label>
              <select
                className="field-select"
                value={local.model || currentProvider.default_model}
                onChange={e => updateActiveProfile({ model: e.target.value })}
              >
                {currentProvider.models.map(m => (
                  <option key={m} value={m}>{m}{m === currentProvider.default_model ? ' (default)' : ''}</option>
                ))}
              </select>
            </>
          )}
        </div>

        <div className="drawer-footer">
          <button className="btn-save" type="button" onClick={handleSave}>Save Settings</button>
        </div>
      </div>
    </div>
  );
}

function providerIcon(id) {
  switch (id) {
    case 'ollama': return '🖥️';
    case 'gemini': return '💎';
    case 'groq': return '⚡';
    case 'openai': return '🤖';
    case 'anthropic': return '🔮';
    default: return '🔧';
  }
}
