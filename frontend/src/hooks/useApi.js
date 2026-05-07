import { useAuth } from "./useAuth";

const API = import.meta.env.VITE_API_URL ?? "http://localhost:8000/api/v1";

export function useApi() {
  const { token } = useAuth();

  async function request(endpoint, options = {}) {
    const headers = {
      ...options.headers,
    };

    if (token) {
      headers["Authorization"] = `Bearer ${token}`;
    }

    const res = await fetch(`${API}${endpoint}`, {
      ...options,
      headers,
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail ?? `Request failed: ${res.status}`);
    }

    return res.json();
  }

  return { request };
}
