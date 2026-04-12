/**
 * store/useSettingsStore.js — Zustand store for provider / API-key settings.
 *
 * Replaces the useSettings hook's local useState with a global Zustand store
 * so any component can read or update settings without prop drilling.
 * Persists to localStorage on every update (same behaviour as the hook).
 */

import { create } from 'zustand';

const STORAGE_KEY = 'fbt-mock-settings';
const PROVIDER_IDS = ['ollama', 'gemini', 'groq', 'openai', 'anthropic'];
const DEFAULT_PROFILE = { model: '', apiKey: '' };

function createProfiles() {
  return PROVIDER_IDS.reduce((acc, id) => {
    acc[id] = { ...DEFAULT_PROFILE };
    return acc;
  }, {});
}

function normaliseProfiles(profiles = {}) {
  const next = createProfiles();
  for (const id of PROVIDER_IDS) {
    const saved = profiles?.[id];
    next[id] = { model: saved?.model || '', apiKey: saved?.apiKey || '' };
  }
  return next;
}

function normaliseSettings(raw = {}) {
  const provider = PROVIDER_IDS.includes(raw.provider) ? raw.provider : 'gemini';
  const profiles = normaliseProfiles(raw.profiles);

  // Migrate older flat apiKey / model into the active provider profile.
  if (raw.apiKey !== undefined || raw.model !== undefined) {
    profiles[provider] = {
      apiKey: raw.apiKey || profiles[provider].apiKey,
      model: raw.model || profiles[provider].model,
    };
  }

  return { provider, profiles };
}

function toView(raw) {
  const active = raw.profiles[raw.provider] || DEFAULT_PROFILE;
  return { ...raw, apiKey: active.apiKey, model: active.model };
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

function load() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return normaliseSettings();
    return normaliseSettings(JSON.parse(raw));
  } catch {
    return normaliseSettings();
  }
}

function persist(s) {
  try { localStorage.setItem(STORAGE_KEY, JSON.stringify(s)); } catch { /* ignore */ }
}

export const useSettingsStore = create((set, get) => ({
  // Raw settings (provider + per-provider profiles)
  _raw: load(),

  // Derived view (flattens active profile's apiKey/model to top level)
  get settings() { return toView(get()._raw); },

  update(patch) {
    set(state => {
      const next = mergeSettings(state._raw, patch);
      persist(next);
      return { _raw: next };
    });
  },
}));

/** Convenience selector — returns the view-form settings object. */
export function useSettings() {
  const raw = useSettingsStore(s => s._raw);
  const update = useSettingsStore(s => s.update);
  return { settings: toView(raw), update };
}
