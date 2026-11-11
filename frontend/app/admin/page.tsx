"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { AdminLessonManager } from "../../components/AdminLessonManager";
import { api, type KnowledgeDocument, type Lesson } from "../../lib/api";

type AuthState = "checking" | "authenticated" | "error";

export default function AdminPage() {
  const router = useRouter();
  const [authState, setAuthState] = useState<AuthState>("checking");
  const [adminToken, setAdminToken] = useState<string | null>(null);
  const [adminUsername, setAdminUsername] = useState("");
  const [lessons, setLessons] = useState<Lesson[]>([]);
  const [documents, setDocuments] = useState<KnowledgeDocument[]>([]);
  const [isLoadingData, setIsLoadingData] = useState(false);
  const [dashboardError, setDashboardError] = useState<string | null>(null);
  const [authError, setAuthError] = useState<string | null>(null);

  const loadDashboardData = useCallback(async (token: string) => {
    setIsLoadingData(true);
    setDashboardError(null);
    try {
      const [lessonData, documentData] = await Promise.all([
        api.getLessons(),
        api.getAdminDocuments(token),
      ]);
      setLessons(Array.isArray(lessonData) ? lessonData : []);
      setDocuments(Array.isArray(documentData) ? documentData : []);
    } catch (err) {
      setDashboardError(err instanceof Error ? err.message : "Failed to load admin data.");
    } finally {
      setIsLoadingData(false);
    }
  }, []);

  const verifyAdmin = useCallback(async () => {
    setAuthState("checking");
    setAuthError(null);
    const savedToken = localStorage.getItem("rag_admin_token");
    if (!savedToken) {
      router.replace("/login");
      return;
    }

    try {
      const admin = await api.adminVerify(savedToken);
      if (!admin) {
        localStorage.removeItem("rag_admin_token");
        router.replace("/login");
        return;
      }
      setAdminToken(savedToken);
      setAdminUsername(admin.username);
      setAuthState("authenticated");
      await loadDashboardData(savedToken);
    } catch (err) {
      setAuthError(err instanceof Error ? err.message : "Could not verify your admin session.");
      setAuthState("error");
    }
  }, [loadDashboardData, router]);

  useEffect(() => {
    void verifyAdmin();
  }, [verifyAdmin]);

  const handleLogout = () => {
    localStorage.removeItem("rag_admin_token");
    setAdminToken(null);
    router.replace("/login");
  };

  const refreshAdminData = () => {
    if (adminToken) void loadDashboardData(adminToken);
  };

  if (authState === "checking") {
    return (
      <main className="flex min-h-dvh items-center justify-center bg-[#07080E] text-sm text-gray-400" role="status">
        Verifying admin access...
      </main>
    );
  }

  if (authState === "error") {
    return (
      <main className="flex min-h-dvh flex-col items-center justify-center gap-4 bg-[#07080E] px-4 text-center text-white">
        <p className="text-sm text-red-300" role="alert">{authError}</p>
        <button
          type="button"
          onClick={() => void verifyAdmin()}
          className="rounded-lg bg-purple-600 px-4 py-2 text-sm font-medium hover:bg-purple-500"
        >
          Retry
        </button>
        <Link href="/login" className="text-sm text-gray-400 hover:text-white">Go to sign in</Link>
      </main>
    );
  }

  return (
    <div className="flex h-screen h-dvh max-h-screen max-h-dvh flex-col overflow-hidden bg-[#07080E] text-white">
      <header className="shrink-0 flex items-center justify-between border-b border-white/10 bg-[#0F101A] px-4 py-4 sm:px-6">
        <div>
          <p className="text-xs font-bold tracking-wider text-purple-300">ADMIN DASHBOARD</p>
          <h1 className="mt-1 text-lg font-semibold">Ruixen AI</h1>
          <p className="mt-1 text-sm text-gray-400">Signed in as {adminUsername}</p>
        </div>
        <Link href="/" className="text-sm text-gray-400 transition hover:text-white">
          Back to chat
        </Link>
      </header>
      <main className="flex-1 min-h-0 overflow-y-auto px-4 py-5 sm:px-6">
        {!adminToken ? null : isLoadingData ? (
          <p className="py-8 text-center text-sm text-gray-400" role="status">Loading dashboard...</p>
        ) : dashboardError ? (
          <div className="mx-auto max-w-3xl rounded-xl border border-red-500/30 bg-red-950/40 p-5 text-sm text-red-300">
            <p role="alert">{dashboardError}</p>
            <button
              type="button"
              onClick={refreshAdminData}
              className="mt-3 rounded-lg bg-white/10 px-3 py-2 font-medium text-white hover:bg-white/15"
            >
              Retry loading
            </button>
            <button
              type="button"
              onClick={handleLogout}
              className="ml-3 text-gray-300 hover:text-white"
            >
              Logout
            </button>
          </div>
        ) : (
          <AdminLessonManager
            adminToken={adminToken}
            lessons={lessons}
            documents={documents}
            onLessonsUpdated={refreshAdminData}
            onLogout={handleLogout}
          />
        )}
      </main>
    </div>
  );
}
