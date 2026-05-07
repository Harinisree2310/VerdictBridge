import React, { useCallback, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../hooks/useAuth";
import { useApi } from "../hooks/useApi";

const ACCEPTED = ".pdf,.png,.jpg,.jpeg,.tiff";

export default function UploadPage() {
  const [file, setFile] = useState(null);
  const [dragging, setDragging] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState(null);
  const navigate = useNavigate();
  const { token } = useAuth();
  const { request } = useApi();

  const handleFile = (f) => {
    setError(null);
    setFile(f);
  };

  const onDrop = useCallback((e) => {
    e.preventDefault();
    setDragging(false);
    const f = e.dataTransfer.files[0];
    if (f) handleFile(f);
  }, []);

  const onDragOver = (e) => {
    e.preventDefault();
    setDragging(true);
  };

  const onDragLeave = () => setDragging(false);

  const onFileChange = (e) => {
    if (e.target.files[0]) handleFile(e.target.files[0]);
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!file) return;

    setError(null);
    setUploading(true);

    try {
      const formData = new FormData();
      formData.append("file", file);
      const uploadRes = await fetch("http://localhost:8000/api/v1/upload/", {
        method: "POST",
        body: formData,
        headers: {
          "Authorization": `Bearer ${token}`,
        },
      });
      if (!uploadRes.ok) {
        const err = await uploadRes.json();
        throw new Error(err.detail ?? "Upload failed.");
      }
      const document = await uploadRes.json();

      navigate(`/review/${document.id}`);
    } catch (err) {
      setError(err.message);
    } finally {
      setUploading(false);
    }
  };

  const busy = uploading;

  return (
    <div className="max-w-xl mx-auto space-y-6">
      <h1 className="text-2xl font-bold">Upload Document</h1>

      <form onSubmit={handleSubmit} className="space-y-4">
        {/* Drop zone */}
        <div
          onDrop={onDrop}
          onDragOver={onDragOver}
          onDragLeave={onDragLeave}
          className={`border-2 border-dashed rounded-xl p-10 text-center cursor-pointer transition-colors ${
            dragging
              ? "border-indigo-400 bg-indigo-900/20"
              : "border-gray-600 hover:border-gray-400"
          }`}
          onClick={() => document.getElementById("file-input").click()}
          role="button"
          aria-label="File drop zone"
          tabIndex={0}
          onKeyDown={(e) => e.key === "Enter" && document.getElementById("file-input").click()}
        >
          <input
            id="file-input"
            type="file"
            accept={ACCEPTED}
            className="hidden"
            onChange={onFileChange}
            aria-label="Select file"
          />
          {file ? (
            <div className="space-y-1">
              <p className="text-indigo-300 font-medium">{file.name}</p>
              <p className="text-gray-400 text-sm">{(file.size / 1024).toFixed(1)} KB</p>
            </div>
          ) : (
            <div className="space-y-2">
              <p className="text-gray-300">Drag & drop a file here, or click to browse</p>
              <p className="text-gray-500 text-sm">PDF, PNG, JPG, TIFF — max 50 MB</p>
            </div>
          )}
        </div>

        {error && (
          <div className="bg-red-900/40 border border-red-600 text-red-300 rounded-lg px-4 py-3 text-sm">
            {error}
          </div>
        )}

        {/* Status messages */}
        {uploading && (
          <p className="text-yellow-400 text-sm animate-pulse">Uploading and extracting document…</p>
        )}

        <button
          type="submit"
          disabled={!file || busy}
          className="w-full bg-indigo-600 hover:bg-indigo-500 disabled:bg-gray-700 disabled:cursor-not-allowed text-white font-semibold py-3 rounded-xl transition-colors"
        >
          {busy ? "Processing…" : "Upload & Extract"}
        </button>
      </form>
    </div>
  );
}
