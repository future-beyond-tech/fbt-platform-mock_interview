import { useState, useCallback } from 'react';

const STORAGE_KEY = 'sheikh-mock-settings';
const PROVIDER_IDS = ['ollama', 'gemini', 'groq', 'openai', 'anthropic'];
const DEFAULT_PROFILE = { model: '', apiKey: '' };

function createProfiles() {
  return PROVIDER_IDS.reduce((acc, providerId) => {
    acc[providerId] = { ...DEFAULT_PROFILE };
    return acc;
  }, {});
}

function normaliseProfiles(profiles = {}) {
  const next = createProfiles();

  for (const providerId of PROVIDER_IDS) {
    const saved = profiles?.[providerId];
    next[providerId] = {
      model: saved?.model || '',
      apiKey: saved?.apiKey || '',
    };
  }

  return next;
}

function normaliseSettings(raw = {}) {
  const provider = PROVIDER_IDS.includes(raw.provider) ? raw.provider : 'gemini';
  const profiles = normaliseProfiles(raw.profiles);

  // Migrate older flat settings into the active provider profile.
  if (raw.apiKey !== undefined || raw.model !== undefined) {
    profiles[provider] = {
      apiKey: raw.apiKey || profiles[provider].apiKey,
      model: raw.model || profiles[provider].model,
    };
  }

  return { provider, profiles };
}

function toView(rawSettings) {
  const active = rawSettings.profiles[rawSettings.provider] || DEFAULT_PROFILE;
  return {
    ...rawSettings,
    apiKey: active.apiKey,
    model: active.model,
  };
}

function load() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return normaliseSettings();
    return normaliseSettings(JSON.parse(raw));
  } catch {
    return normaliseSettings();
  }
}

function mergeSettings(prev, patch) {
  const provider = patch.provider ?? prev.provider;
  const next = normaliseSettings({
    ...prev,
    ...patch,
    profiles: patch.profiles ? { ...prev.profiles, ...patch.profiles } : prev.profiles,
  });

  if (Object.prototype.hasOwnProperty.call(patch, 'apiKey') || Object.prototype.hasOwnProperty.call(patch, 'model')) {
    next.profiles[provider] = {
      ...next.profiles[provider],
      ...(Object.prototype.hasOwnProperty.call(patch, 'apiKey') ? { apiKey: patch.apiKey || '' } : {}),
      ...(Object.prototype.hasOwnProperty.call(patch, 'model') ? { model: patch.model || '' } : {}),
    };
  }

  return normaliseSettings(next);
}

function save(settings) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(settings));
  } catch { /* ignore */ }
}

export function useSettings() {
  const [rawSettings, setRawSettings] = useState(load);

  const update = useCallback((patch) => {
    setRawSettings(prev => {
      const next = mergeSettings(prev, patch);
      save(next);
      return next;
    });
  }, []);

  return { settings: toView(rawSettings), update };
}
