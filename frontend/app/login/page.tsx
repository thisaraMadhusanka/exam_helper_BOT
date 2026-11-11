"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { api } from "../../lib/api";

export default function LoginPage() {
  const router = useRouter();
  const [accessCode, setAccessCode] = useState("");
  const [showCode, setShowCode] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [isCheckingSavedToken, setIsCheckingSavedToken] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;

    const checkSavedToken = async () => {
      const savedToken = localStorage.getItem("rag_admin_token");
      if (!savedToken) {
        setIsCheckingSavedToken(false);
        return;
      }

      try {
        const admin = await api.adminVerify(savedToken);
        if (!active) return;
        if (admin) {
          router.replace("/admin");
          return;
        }
        localStorage.removeItem("rag_admin_token");
      } catch {
        if (active) {
          setError("Could not verify your saved session. Please enter access code.");
        }
      } finally {
        if (active) setIsCheckingSavedToken(false);
      }
    };

    void checkSavedToken();
    return () => {
      active = false;
    };
  }, [router]);

  const handleSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const cleanCode = accessCode.replace(/\s+/g, "").toUpperCase();
    if (!cleanCode) return;

    setIsLoading(true);
    setError(null);
    try {
      const response = await api.adminLoginWithCode(cleanCode);
      localStorage.setItem("rag_admin_token", response.access_token);
      router.replace("/admin");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Invalid admin access code. Please try again.");
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <main className="flex min-h-dvh items-center justify-center bg-[#07080E] px-4 py-10 text-white">
      <section className="w-full max-w-md rounded-2xl border border-white/10 bg-[#121320] p-7 shadow-2xl sm:p-8">
        <Link href="/" className="text-sm font-semibold text-purple-300 hover:text-purple-200">
          Ruixen AI
        </Link>
        <div className="mb-7 mt-8">
          <div className="mb-3 flex h-11 w-11 items-center justify-center rounded-xl bg-purple-500/15 text-purple-300">
            <svg className="h-6 w-6" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
            </svg>
          </div>
          <h1 className="text-2xl font-bold">Admin Portal</h1>
          <p className="mt-2 text-sm text-gray-400">
            Enter your secret admin access code to manage lessons and the knowledge base.
          </p>
        </div>

        {isCheckingSavedToken ? (
          <p className="text-sm text-gray-400" role="status">Checking your saved session...</p>
        ) : (
          <form onSubmit={handleSubmit} className="space-y-5">
            {error && (
              <p className="rounded-lg border border-red-500/30 bg-red-950/40 p-3 text-sm text-red-300" role="alert">
                {error}
              </p>
            )}
            <div>
              <label htmlFor="admin-code" className="mb-2 block text-sm font-medium text-gray-300">
                Admin Access Code
              </label>
              <div className="relative">
                <input
                  id="admin-code"
                  type={showCode ? "text" : "password"}
                  value={accessCode}
                  onChange={(event) => setAccessCode(event.target.value)}
                  autoComplete="off"
                  autoFocus
                  required
                  className="w-full rounded-lg border border-white/10 bg-black/40 px-4 py-3 pr-10 font-mono text-sm tracking-wider text-white outline-none transition focus:border-purple-500 focus:ring-2 focus:ring-purple-500/30"
                  placeholder="Enter admin access code"
                />
                <button
                  type="button"
                  onClick={() => setShowCode(!showCode)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-white"
                  aria-label={showCode ? "Hide access code" : "Show access code"}
                >
                  {showCode ? (
                    <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13.875 18.825A10.05 10.05 0 0112 19c-4.478 0-8.268-2.943-9.543-7a9.97 9.97 0 011.563-3.029m5.858.908a3 3 0 114.243 4.243M9.878 9.878l4.242 4.242M9.88 9.88l-3.29-3.29m7.532 7.532l3.29 3.29M3 3l18 18" />
                    </svg>
                  ) : (
                    <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
                    </svg>
                  )}
                </button>
              </div>
            </div>

            <button
              type="submit"
              disabled={isLoading || !accessCode.trim()}
              className="w-full rounded-lg bg-gradient-to-r from-purple-600 to-indigo-600 px-4 py-3 text-sm font-semibold text-white shadow-lg shadow-purple-900/30 transition hover:from-purple-500 hover:to-indigo-500 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {isLoading ? "Verifying..." : "Unlock Admin Dashboard"}
            </button>
          </form>
        )}
      </section>
    </main>
  );
}
