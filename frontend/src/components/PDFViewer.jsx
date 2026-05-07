import React, { useState, useEffect, useRef } from "react";

/**
 * PDFViewer — fetches the PDF with the stored Bearer token,
 * converts it to a blob URL, and renders it in an iframe.
 *
 * Why the blob approach:
 *   Browsers cannot send an Authorization header from an <iframe src=...>.
 *   We fetch() the file in JS (where we can set headers), get the bytes,
 *   create a temporary object URL, and hand that to the iframe.
 *   The blob URL is revoked on unmount to free memory.
 */
export default function PDFViewer({ fileUrl, title = "Document preview" }) {
  const [blobUrl, setBlobUrl]   = useState(null);
  const [loading, setLoading]   = useState(false);
  const [loadError, setLoadError] = useState(null);
  const blobRef = useRef(null);

  useEffect(() => {
    if (!fileUrl) return;

    let cancelled = false;
    setLoading(true);
    setLoadError(null);
    setBlobUrl(null);

    const token = localStorage.getItem("auth_token");

    fetch(fileUrl, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    })
      .then((res) => {
        if (!res.ok) throw new Error(`Server returned ${res.status}`);
        return res.blob();
      })
      .then((blob) => {
        if (cancelled) return;
        const url = URL.createObjectURL(blob);
        blobRef.current = url;
        setBlobUrl(url);
      })
      .catch((err) => {
        if (!cancelled) setLoadError(err.message);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
      // Revoke previous blob URL to free memory
      if (blobRef.current) {
        URL.revokeObjectURL(blobRef.current);
        blobRef.current = null;
      }
    };
  }, [fileUrl]);

  // ── No URL yet ─────────────────────────────────────────────────────────────
  if (!fileUrl) {
    return (
      <div className="bg-gray-800 rounded-xl flex items-center justify-center h-96 text-gray-400 text-sm">
        No document URL provided.
      </div>
    );
  }

  // ── Loading ─────────────────────────────────────────────────────────────────
  if (loading) {
    return (
      <div className="bg-gray-800 rounded-xl flex flex-col items-center justify-center h-96 gap-3 text-gray-400 text-sm">
        <div className="w-6 h-6 border-2 border-indigo-400 border-t-transparent rounded-full animate-spin" />
        <span>Loading document…</span>
      </div>
    );
  }

  // ── Error ───────────────────────────────────────────────────────────────────
  if (loadError) {
    return (
      <div className="bg-gray-800 rounded-xl flex flex-col items-center justify-center h-96 gap-3 text-gray-400 text-sm">
        <span className="text-red-400">⚠ Preview unavailable</span>
        <span className="text-xs text-gray-500">{loadError}</span>
        <a
          href={fileUrl}
          target="_blank"
          rel="noopener noreferrer"
          className="text-indigo-400 hover:text-indigo-300 underline text-xs"
        >
          Try opening in new tab ↗
        </a>
      </div>
    );
  }

  // ── Render blob in iframe ───────────────────────────────────────────────────
  return (
    <div className="bg-gray-800 rounded-xl overflow-hidden shadow">
      <div className="px-4 py-3 border-b border-gray-700 flex items-center justify-between">
        <span className="text-sm font-medium text-gray-300">Document Preview</span>
        {blobUrl && (
          <a
            href={blobUrl}
            download={title}
            className="text-xs text-indigo-400 hover:text-indigo-300 underline"
          >
            Download ↓
          </a>
        )}
      </div>
      {blobUrl && (
        <iframe
          src={blobUrl}
          title={title}
          className="w-full"
          style={{ height: "70vh", border: "none" }}
          aria-label={title}
        />
      )}
    </div>
  );
}
