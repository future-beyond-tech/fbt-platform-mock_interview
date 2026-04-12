/**
 * hooks/useSettings.js — Backward-compatibility shim.
 *
 * Phase 9: Settings state has moved to src/store/useSettingsStore.js (Zustand).
 * This file re-exports the hook so any code still importing from here continues to work.
 */

export { useSettings } from '../store/useSettingsStore';
