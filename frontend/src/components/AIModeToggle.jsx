import React, { useEffect, useState, useCallback } from "react";
import { useAuth } from "../hooks/useAuth";

const API = import.meta.env.VITE_API_URL ?? "http://localhost:8000/api/v1";

/**
 * AIModeToggle — floating pill in the bottom-right corner.
 * Lets operators switch the extraction engine between real AI and Mock
 * at runtime without touching the server config.
 */
export default function AIModeToggle() {
  const { token, user } = useAuth();
  const [mode, setMode] = useState(null);        // "ai" | "mock" | null
  const [providers, setProviders] = useState({}); // { claude, gemini, openai }
  const [busy, setBusy] = useState(false);
  const [showInfo, setShowInfo] = useState(false);

  const fetchMode = useCallback(async () => {
    if (!token) return;
    try {
      // POST /ai/reload forces the backend to re-read .env before reporting
      // provider status — ensures API keys added after startup are visible.
      const res = await fetch(`${API}/ai/reload`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) {
        const data = await res.json();
        setMode(data.mode);
        setProviders(data.providers_configured ?? {});
      }
    } catch { /* silent */ }
  }, [token]);

  useEffect(() => {
    fetchMode();
  }, [fetchMode]);

  if (!user || mode === null) return null;

  const isMock = mode === "mock";
  const hasAnyKey = providers.claude || providers.gemini || providers.openai;

  async function toggle() {
    if (busy) return;
    setBusy(true);
    const next = isMock ? "ai" : "mock";
    try {
      const res = await fetch(`${API}/ai/mode`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ mode: next }),
      });
      if (res.ok) {
        const data = await res.json();
        setMode(data.mode);
        setProviders(data.providers_configured ?? {});
      }
    } catch { /* silent */ } finally {
      setBusy(false);
    }
  }

  return (
    <div className="fixed bottom-4 right-4 z-50 flex flex-col items-end gap-2">
      {/* Info tooltip */}
      {showInfo && (
        <div className="bg-gray-800 border border-gray-600 rounded-lg px-3 py-2 text-xs text-gray-300 shadow-xl max-w-xs">
          <p className="font-semibold text-white mb-1">LLM Providers configured:</p>
          <ul className="space-y-0.5">
            {[["Claude", providers.claude], ["Gemini", providers.gemini], ["OpenAI", providers.openai]].map(
              ([name, active]) => (
                <li key={name} className="flex items-center gap-1.5">
                  <span className={active ? "text-green-400" : "text-gray-500"}>
                    {active ? "✓" : "✗"}
                  </span>
                  <span className={active ? "text-gray-200" : "text-gray-500"}>{name}</span>
                </li>
              )
            )}
          </ul>
          {!hasAnyKey && (
            <p className="text-yellow-400 mt-1.5 text-[11px]">
              No API keys set — AI mode will fall back to Mock.
            </p>
          )}
        </div>
      )}

      {/* Toggle pill */}
      <div className="flex items-center gap-2 bg-gray-800 border border-gray-600 rounded-full px-3 py-1.5 shadow-xl">
        {/* Info button */}
        <button
          onClick={() => setShowInfo((s) => !s)}
          className="text-gray-400 hover:text-gray-200 text-xs transition-colors"
          title="Provider info"
        >
          ⓘ
        </button>

        {/* Label */}
        <span className="text-xs text-gray-400 select-none">Extraction:</span>

        {/* Toggle switch */}
        <button
          onClick={toggle}
          disabled={busy}
          title={isMock ? "Switch to AI mode" : "Switch to Mock mode"}
          className={`relative inline-flex items-center w-10 h-5 rounded-full transition-colors duration-300 focus:outline-none ${
            isMock
              ? "bg-gray-600"
              : "bg-indigo-600"
          } ${busy ? "opacity-50 cursor-wait" : "cursor-pointer"}`}
        >
          <span
            className={`inline-block w-4 h-4 bg-white rounded-full shadow transform transition-transform duration-300 ${
              isMock ? "translate-x-0.5" : "translate-x-5"
            }`}
          />
        </button>

        {/* Mode label */}
        <span
          className={`text-xs font-semibold w-8 select-none ${
            isMock ? "text-gray-400" : "text-indigo-400"
          }`}
        >
          {isMock ? "Mock" : "AI"}
        </span>
      </div>
    </div>
  );
}
