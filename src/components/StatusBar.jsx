export default function StatusBar({ provider, settings, health, onOpenSettings }) {
  const pName = provider ? provider.name : settings.provider;
  const needsKey = provider?.needs_key && !provider?.server_key_available && !settings.apiKey;
  const backendOffline = health?.status === 'unreachable';
  const ollamaOffline = provider?.id === 'ollama' && health && !health.ollama;
  const warn = backendOffline || ollamaOffline || needsKey;

  let text = pName;
  if (backendOffline) text = 'Backend offline';
  else if (ollamaOffline) text = 'Ollama offline';
  else if (needsKey) text = `${pName} — key needed`;
  else if (provider) text = `${pName} ready`;

  return (
    <button className="status-chip" type="button" onClick={onOpenSettings}>
      <span className={`status-led${warn ? ' warn' : ' ok'}`} />
      <span className="status-text">
        {text}
      </span>
      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
        <circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/>
      </svg>
    </button>
  );
}
