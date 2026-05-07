import React, { useEffect, useState, useCallback } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { useApi } from "../hooks/useApi";
import PDFViewer from "../components/PDFViewer";
import FieldEditor from "../components/FieldEditor";

const ACTION_STATUS_COLORS = {
  pending: "text-yellow-400",
  completed: "text-green-400",
  skipped: "text-gray-400",
};

export default function ReviewPage() {
  const { documentId } = useParams();
  const navigate = useNavigate();
  const { request } = useApi();

  const [document, setDocument]   = useState(null);
  const [fields, setFields]       = useState([]);
  const [actions, setActions]     = useState([]);
  const [loading, setLoading]     = useState(true);
  const [error, setError]         = useState(null);
  const [saving, setSaving]       = useState(false);
  const [rerunning, setRerunning] = useState(false);
  const [rerunMsg, setRerunMsg]   = useState(null);

  const load = useCallback(async () => {
    try {
      const [doc, fieldsData, actionsData] = await Promise.all([
        request(`/dashboard/documents/${documentId}`),
        request(`/review/${documentId}/fields`),
        request(`/review/${documentId}/actions`),
      ]);
      setDocument(doc);
      setFields(fieldsData);
      setActions(actionsData);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [documentId]);

  useEffect(() => {
    load();
  }, [load]);

  // ── Re-run extraction ────────────────────────────────────────────────────────
  const handleRerun = async () => {
    setRerunning(true);
    setRerunMsg(null);
    try {
      await request(`/extraction/${documentId}/retry`, { method: "POST" });
      setRerunMsg("Extraction complete — reloading…");
      // Reload all data
      setLoading(true);
      await load();
    } catch (err) {
      setRerunMsg(`Re-run failed: ${err.message}`);
    } finally {
      setRerunning(false);
    }
  };

  // ── Field save ───────────────────────────────────────────────────────────────
  const handleFieldSave = async (fieldId, newValue) => {
    const updated = await request(`/review/${documentId}/fields/${fieldId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ field_value: newValue }),
    });
    setFields((prev) => prev.map((f) => (f.id === fieldId ? updated : f)));
  };

  // ── Action status ────────────────────────────────────────────────────────────
  const handleActionStatus = async (actionId, newStatus) => {
    const updated = await request(`/review/${documentId}/actions/${actionId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status: newStatus }),
    });
    setActions((prev) => prev.map((a) => (a.id === actionId ? updated : a)));
  };

  // ── Approve / Reject ─────────────────────────────────────────────────────────
  const handleDecision = async (decision) => {
    setSaving(true);
    try {
      await request(`/review/${documentId}/${decision}`, { method: "POST" });
      navigate("/");
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  };

  if (loading) return (
    <div className="flex items-center justify-center h-64 gap-3 text-gray-400">
      <div className="w-5 h-5 border-2 border-indigo-400 border-t-transparent rounded-full animate-spin" />
      Loading review…
    </div>
  );
  if (error) return <p className="text-red-400">Error: {error}</p>;

  const noData = fields.length === 0 && actions.length === 0;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold">{document.original_filename}</h1>
          <p className="text-gray-400 text-sm mt-1">
            Status:{" "}
            <span className={`font-medium ${
              document.status === "extracted" || document.status === "approved"
                ? "text-green-400"
                : document.status === "failed"
                ? "text-red-400"
                : "text-indigo-300"
            }`}>
              {document.status}
            </span>
            {document.page_count && ` · ${document.page_count} page(s)`}
            {document.llm_provider_used && (
              <span className="ml-2 text-xs text-gray-500">
                via <span className="text-indigo-400">{document.llm_provider_used}</span>
              </span>
            )}
          </p>
          {document.extraction_error && (
            <p className="text-red-400 text-xs mt-1">{document.extraction_error}</p>
          )}
        </div>

        <div className="flex gap-2 flex-wrap justify-end">
          {/* Re-run button — shown when no data or failed */}
          {(noData || document.status === "failed" || document.status === "queued") && (
            <button
              onClick={handleRerun}
              disabled={rerunning}
              className="px-4 py-2 rounded-lg bg-indigo-700 hover:bg-indigo-600 disabled:opacity-50 text-white text-sm font-medium transition-colors flex items-center gap-2"
            >
              {rerunning ? (
                <>
                  <span className="w-3.5 h-3.5 border-2 border-white border-t-transparent rounded-full animate-spin" />
                  Running…
                </>
              ) : (
                "⚡ Run Extraction"
              )}
            </button>
          )}
          <button
            onClick={() => handleDecision("reject")}
            disabled={saving}
            className="px-4 py-2 rounded-lg bg-red-700 hover:bg-red-600 disabled:opacity-50 text-white text-sm font-medium transition-colors"
          >
            Reject
          </button>
          <button
            onClick={() => handleDecision("approve")}
            disabled={saving}
            className="px-4 py-2 rounded-lg bg-green-700 hover:bg-green-600 disabled:opacity-50 text-white text-sm font-medium transition-colors"
          >
            Approve
          </button>
        </div>
      </div>

      {/* Re-run status message */}
      {rerunMsg && (
        <div className={`text-sm px-4 py-2 rounded-lg ${
          rerunMsg.includes("failed") ? "bg-red-900/40 text-red-300" : "bg-indigo-900/40 text-indigo-300"
        }`}>
          {rerunMsg}
        </div>
      )}

      {/* Body */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Left: PDF viewer */}
        <PDFViewer
          fileUrl={`http://localhost:8000/api/v1/dashboard/files/${document.filename}`}
          title={document.original_filename}
        />

        {/* Right: Fields + Actions */}
        <div className="space-y-6">
          {/* Extracted fields */}
          <div className="bg-gray-800 rounded-xl shadow overflow-hidden">
            <div className="px-5 py-4 border-b border-gray-700 flex items-center justify-between">
              <h2 className="font-semibold">Extracted Fields</h2>
              {fields.length > 0 && (
                <span className="text-xs text-gray-400">{fields.length} field(s)</span>
              )}
            </div>
            <div className="divide-y divide-gray-700">
              {fields.length === 0 ? (
                <div className="px-5 py-6 text-center">
                  <p className="text-gray-400 text-sm">No fields extracted yet.</p>
                  {!rerunning && (
                    <p className="text-gray-500 text-xs mt-1">
                      Click <span className="text-indigo-400">⚡ Run Extraction</span> above to analyse this document.
                    </p>
                  )}
                </div>
              ) : (
                fields.map((field) => (
                  <FieldEditor key={field.id} field={field} onSave={handleFieldSave} />
                ))
              )}
            </div>
          </div>

          {/* Actions */}
          <div className="bg-gray-800 rounded-xl shadow overflow-hidden">
            <div className="px-5 py-4 border-b border-gray-700">
              <h2 className="font-semibold">Required Actions</h2>
            </div>
            <div className="divide-y divide-gray-700">
              {actions.length === 0 ? (
                <p className="px-5 py-4 text-gray-400 text-sm">No actions suggested.</p>
              ) : (
                actions.map((action) => (
                  <div key={action.id} className="px-5 py-4 flex items-start justify-between gap-4">
                    <div className="space-y-0.5">
                      <p className="font-medium text-sm">{action.description ?? action.action_type}</p>
                      <p className="text-gray-400 text-xs">
                        Dept: {action.responsible_dept ?? "—"}
                      </p>
                      {action.due_date && (
                        <p className="text-gray-400 text-xs">
                          Due: {new Date(action.due_date).toLocaleDateString("en-IN", {
                            day: "numeric", month: "short", year: "numeric"
                          })}
                        </p>
                      )}
                      <p className={`text-xs font-semibold ${ACTION_STATUS_COLORS[action.status] ?? "text-gray-300"}`}>
                        {action.status}
                      </p>
                    </div>
                    <div className="flex gap-2 shrink-0">
                      <button
                        onClick={() => handleActionStatus(action.id, "completed")}
                        disabled={action.status === "completed"}
                        className="text-xs px-2 py-1 rounded bg-green-800 hover:bg-green-700 disabled:opacity-40 text-white transition-colors"
                      >
                        Done
                      </button>
                      <button
                        onClick={() => handleActionStatus(action.id, "skipped")}
                        disabled={action.status === "skipped"}
                        className="text-xs px-2 py-1 rounded bg-gray-700 hover:bg-gray-600 disabled:opacity-40 text-white transition-colors"
                      >
                        Skip
                      </button>
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
