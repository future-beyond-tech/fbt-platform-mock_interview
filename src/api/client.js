/**
 * api/client.js — Shared base URL and error-extraction helper.
 *
 * Every feature module imports from here so the API root is defined once.
 */

export const BASE = import.meta.env.VITE_API_URL || '';

/**
 * Extract the human-readable detail string from a failed response.
 * Falls back to a generic status message.
 */
export async function extractErrorDetail(res) {
  try {
    const d = await res.json();
    return d.detail || `HTTP ${res.status}`;
  } catch {
    try {
      return await res.text() || `HTTP ${res.status}`;
    } catch {
      return `HTTP ${res.status}`;
    }
  }
}
