import React, { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useApi } from "../hooks/useApi";

const STATUS_COLORS = {
  uploaded: "bg-gray-600",
  extracting: "bg-yellow-600",
  extracted: "bg-blue-600",
  reviewing: "bg-purple-600",
  approved: "bg-green-600",
  rejected: "bg-red-600",
};

function StatCard({ label, value, color = "text-indigo-400" }) {
  return (
    <div className="bg-gray-800 rounded-xl p-5 flex flex-col gap-1 shadow">
      <span className="text-gray-400 text-sm">{label}</span>
      <span className={`text-3xl font-bold ${color}`}>{value}</span>
    </div>
  );
}

export default function Dashboard() {
  const [stats, setStats] = useState(null);
  const [documents, setDocuments] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const navigate = useNavigate();
  const { request } = useApi();

  useEffect(() => {
    async function load() {
      try {
        const [statsData, docsData] = await Promise.all([
          request("/dashboard/stats"),
          request("/dashboard/documents?limit=20"),
        ]);
        setStats(statsData);
        setDocuments(docsData.items);
      } catch (err) {
        setError(err.message);
      } finally {
        setLoading(false);
      }
    }
    load();
  }, []);

  if (loading) return <p className="text-gray-400">Loading dashboard…</p>;
  if (error) return <p className="text-red-400">Error: {error}</p>;

  return (
    <div className="space-y-8">
      <h1 className="text-2xl font-bold">Dashboard</h1>

      {/* Stats */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <StatCard label="Total Documents" value={stats.total_documents} />
        <StatCard label="Pending Actions" value={stats.pending_actions} color="text-yellow-400" />
        <StatCard label="Approved" value={stats.by_status.approved ?? 0} color="text-green-400" />
        <StatCard label="Rejected" value={stats.by_status.rejected ?? 0} color="text-red-400" />
      </div>

      {/* Document table */}
      <div className="bg-gray-800 rounded-xl shadow overflow-hidden">
        <div className="px-6 py-4 border-b border-gray-700 flex items-center justify-between">
          <h2 className="font-semibold text-lg">Documents</h2>
          <button
            onClick={() => navigate("/upload")}
            className="bg-indigo-600 hover:bg-indigo-500 text-white text-sm px-4 py-2 rounded-lg transition-colors"
          >
            + Upload
          </button>
        </div>
        {documents.length === 0 ? (
          <p className="px-6 py-8 text-gray-400 text-center">No documents yet. Upload one to get started.</p>
        ) : (
          <table className="w-full text-sm">
            <thead className="bg-gray-700 text-gray-300 uppercase text-xs">
              <tr>
                <th className="px-6 py-3 text-left">Filename</th>
                <th className="px-6 py-3 text-left">Status</th>
                <th className="px-6 py-3 text-left">Pages</th>
                <th className="px-6 py-3 text-left">Uploaded</th>
                <th className="px-6 py-3 text-left">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-700">
              {documents.map((doc) => (
                <tr key={doc.id} className="hover:bg-gray-750 transition-colors">
                  <td className="px-6 py-4 font-medium truncate max-w-xs">{doc.original_filename}</td>
                  <td className="px-6 py-4">
                    <span
                      className={`inline-block px-2 py-0.5 rounded-full text-xs font-semibold text-white ${
                        STATUS_COLORS[doc.status] ?? "bg-gray-600"
                      }`}
                    >
                      {doc.status}
                    </span>
                  </td>
                  <td className="px-6 py-4 text-gray-400">{doc.page_count ?? "—"}</td>
                  <td className="px-6 py-4 text-gray-400">
                    {new Date(doc.uploaded_at).toLocaleDateString()}
                  </td>
                  <td className="px-6 py-4">
                    <button
                      onClick={() => navigate(`/review/${doc.id}`)}
                      className="text-indigo-400 hover:text-indigo-300 underline text-xs"
                    >
                      Review
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
