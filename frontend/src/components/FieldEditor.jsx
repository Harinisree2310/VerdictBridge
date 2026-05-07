import React, { useState } from "react";

/**
 * FieldEditor — inline editor for a single extracted field.
 *
 * Props:
 *   field   — ExtractedField object from the API
 *   onSave  — async (fieldId, newValue) => void
 */
export default function FieldEditor({ field, onSave }) {
  const [editing, setEditing] = useState(false);
  const [value, setValue] = useState(field.field_value ?? "");
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState(null);

  const confidenceColor = () => {
    const score = parseFloat(field.confidence);
    if (isNaN(score)) return "text-gray-500";
    if (score >= 0.85) return "text-green-400";
    if (score >= 0.6) return "text-yellow-400";
    return "text-red-400";
  };

  const handleSave = async () => {
    setSaving(true);
    setSaveError(null);
    try {
      await onSave(field.id, value);
      setEditing(false);
    } catch (err) {
      setSaveError(err.message ?? "Save failed.");
    } finally {
      setSaving(false);
    }
  };

  const handleCancel = () => {
    setValue(field.field_value ?? "");
    setEditing(false);
    setSaveError(null);
  };

  // Format field name for display: case_number → Case Number
  const displayName = field.field_name
    .replace(/_/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());

  return (
    <div className="px-5 py-4 space-y-1">
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <span className="text-xs font-semibold text-gray-400 uppercase tracking-wide">
            {displayName}
          </span>
          {field.confidence && (
            <span className={`text-xs font-mono ${confidenceColor()}`}>
              {(parseFloat(field.confidence) * 100).toFixed(0)}%
            </span>
          )}
          {field.is_edited && (
            <span className="text-xs bg-indigo-800 text-indigo-200 px-1.5 py-0.5 rounded">
              edited
            </span>
          )}
        </div>
        {!editing && (
          <button
            onClick={() => setEditing(true)}
            className="text-xs text-indigo-400 hover:text-indigo-300 transition-colors"
            aria-label={`Edit ${displayName}`}
          >
            Edit
          </button>
        )}
      </div>

      {editing ? (
        <div className="space-y-2">
          <textarea
            value={value}
            onChange={(e) => setValue(e.target.value)}
            rows={3}
            className="w-full bg-gray-700 border border-gray-600 focus:border-indigo-500 focus:outline-none rounded-lg px-3 py-2 text-sm text-gray-100 resize-y"
            aria-label={`Edit value for ${displayName}`}
            autoFocus
          />
          {saveError && <p className="text-red-400 text-xs">{saveError}</p>}
          <div className="flex gap-2">
            <button
              onClick={handleSave}
              disabled={saving}
              className="text-xs px-3 py-1.5 rounded-lg bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white font-medium transition-colors"
            >
              {saving ? "Saving…" : "Save"}
            </button>
            <button
              onClick={handleCancel}
              disabled={saving}
              className="text-xs px-3 py-1.5 rounded-lg bg-gray-700 hover:bg-gray-600 disabled:opacity-50 text-white transition-colors"
            >
              Cancel
            </button>
          </div>
          {field.original_value && field.is_edited && (
            <p className="text-gray-500 text-xs">
              Original: <span className="text-gray-400">{field.original_value}</span>
            </p>
          )}
        </div>
      ) : (
        <p className="text-sm text-gray-200 whitespace-pre-wrap break-words">
          {field.field_value ?? <span className="text-gray-500 italic">Not found</span>}
        </p>
      )}
    </div>
  );
}
