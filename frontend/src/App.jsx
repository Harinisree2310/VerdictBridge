import React from "react";
import { BrowserRouter, Routes, Route, NavLink, useNavigate } from "react-router-dom";
import { AuthProvider, useAuth } from "./hooks/useAuth";
import { ProtectedRoute } from "./components/ProtectedRoute";
import LoginPage from "./pages/LoginPage";
import UploadPage from "./pages/UploadPage";
import ReviewPage from "./pages/ReviewPage";
import Dashboard from "./pages/Dashboard";
import AIModeToggle from "./components/AIModeToggle";
import "./index.css";

function NavBar() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const linkClass = ({ isActive }) =>
    `px-4 py-2 rounded text-sm font-medium transition-colors ${
      isActive
        ? "bg-indigo-600 text-white"
        : "text-gray-300 hover:bg-gray-700 hover:text-white"
    }`;

  if (!user) return null;

  return (
    <nav className="bg-gray-900 shadow-md">
      <div className="max-w-6xl mx-auto px-4 py-3 flex items-center justify-between">
        <div className="flex items-center gap-6">
          <span className="text-white font-bold text-lg tracking-tight">
            ⚖️ VerdictBridge
          </span>
          <NavLink to="/" end className={linkClass}>
            Dashboard
          </NavLink>
          <NavLink to="/upload" className={linkClass}>
            Upload
          </NavLink>
        </div>
        <div className="flex items-center gap-4">
          <span className="text-gray-300 text-sm">{user.email}</span>
          <button
            onClick={() => {
              logout();
              navigate("/login");
            }}
            className="px-4 py-2 rounded text-sm font-medium text-gray-300 hover:bg-gray-700 hover:text-white transition-colors"
          >
            Logout
          </button>
        </div>
      </div>
    </nav>
  );
}

function AppContent() {
  return (
    <div className="min-h-screen bg-gray-950 text-gray-100">
      <NavBar />
      <main className="max-w-6xl mx-auto px-4 py-8">
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route path="/" element={<ProtectedRoute><Dashboard /></ProtectedRoute>} />
          <Route path="/upload" element={<ProtectedRoute><UploadPage /></ProtectedRoute>} />
          <Route path="/review/:documentId" element={<ProtectedRoute><ReviewPage /></ProtectedRoute>} />
        </Routes>
      </main>
      <AIModeToggle />
    </div>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <AppContent />
      </AuthProvider>
    </BrowserRouter>
  );
}
