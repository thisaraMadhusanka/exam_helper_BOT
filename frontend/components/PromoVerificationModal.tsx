"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import { api } from "../lib/api";

interface PromoVerificationModalProps {
  isOpen: boolean;
  onVerified: (code: string, token: string, label?: string) => void;
}

export function PromoVerificationModal({
  isOpen,
  onVerified,
}: PromoVerificationModalProps) {
  const [code, setCode] = useState("");
  const [isVerifying, setIsVerifying] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  // Auto focus input when opened
  useEffect(() => {
    if (isOpen) {
      const timer = setTimeout(() => {
        inputRef.current?.focus();
      }, 150);
      return () => clearTimeout(timer);
    }
  }, [isOpen]);

  const handleVerify = useCallback(
    async (codeToVerify?: string) => {
      const rawCode = (codeToVerify ?? code).trim();
      const targetCode = rawCode.replace(/\s+/g, "").toUpperCase();
      if (!targetCode) {
        setErrorMessage("Please enter an access code.");
        inputRef.current?.focus();
        return;
      }

      setIsVerifying(true);
      setErrorMessage(null);

      try {
        const response = await api.verifyPromoCode(targetCode);
        if (response.valid && response.promo_token) {
          // Store verified credentials in localStorage
          localStorage.setItem("rag_promo_token", response.promo_token);
          localStorage.setItem("rag_promo_code", response.code || targetCode);
          if (response.label) {
            localStorage.setItem("rag_promo_label", response.label);
          }
          if (response.admin_token) {
            localStorage.setItem("rag_admin_token", response.admin_token);
          }
          onVerified(response.code || targetCode, response.promo_token, response.label);
        } else {
          setErrorMessage(response.message || "Invalid access code.");
        }
      } catch (err) {
        const msg =
          err instanceof Error
            ? err.message
            : "Verification failed. Please check the code and try again.";
        setErrorMessage(msg);
      } finally {
        setIsVerifying(false);
      }
    },
    [code, onVerified]
  );

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter") {
      e.preventDefault();
      void handleVerify();
    }
  };

  const handleQuickFill = (sampleCode: string) => {
    setCode(sampleCode);
    setErrorMessage(null);
    void handleVerify(sampleCode);
  };

  if (!isOpen) return null;

  return (
    <div
      id="promo-verification-overlay"
      className="fixed inset-0 z-50 flex items-center justify-center p-4 select-none backdrop-blur-xl bg-black/85"
      role="dialog"
      aria-modal="true"
      aria-labelledby="promo-modal-title"
    >
      {/* Background radial ambient glow */}
      <div className="pointer-events-none absolute -inset-[100px] bg-[radial-gradient(circle_at_center,rgba(99,102,241,0.22)_0%,rgba(147,51,234,0.18)_35%,transparent_70%)] blur-2xl" />

      {/* Main Glassmorphic Card */}
      <div className="relative w-full max-w-md overflow-hidden rounded-3xl border border-white/15 bg-[#12131F]/95 p-6 sm:p-8 shadow-[0_0_60px_rgba(79,70,229,0.35)] backdrop-blur-2xl transition-all animate-in fade-in zoom-in-95 duration-200">
        {/* Top Glow Accent bar */}
        <div className="absolute top-0 left-1/2 h-[3px] w-48 -translate-x-1/2 bg-gradient-to-r from-transparent via-purple-500 to-transparent" />

        <div className="flex flex-col items-center text-center">
          {/* Glowing Lock Badge (matching OTP UI screenshot) */}
          <div className="relative mb-5 flex h-16 w-16 items-center justify-center rounded-2xl bg-gradient-to-br from-blue-500/20 via-purple-500/20 to-indigo-500/20 p-[1px] shadow-[0_0_30px_rgba(139,92,246,0.35)]">
            <div className="flex h-full w-full items-center justify-center rounded-2xl bg-[#171827] border border-white/10">
              <div className="relative flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-tr from-blue-600 to-purple-600 shadow-inner">
                <svg
                  className="h-5 w-5 text-white"
                  fill="none"
                  viewBox="0 0 24 24"
                  stroke="currentColor"
                  strokeWidth={2.2}
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z"
                  />
                </svg>
              </div>
            </div>
          </div>

          {/* Heading and Description */}
          <h2
            id="promo-modal-title"
            className="text-2xl font-bold tracking-tight text-white drop-shadow-sm"
          >
            Access Verification
          </h2>
          <p className="mt-2 text-xs sm:text-sm text-gray-400 max-w-xs leading-relaxed">
            Enter your student access code to unlock the AI tutor chat and start asking questions.
          </p>

          {/* Error Message Pill */}
          {errorMessage && (
            <div
              className="mt-4 flex w-full items-center gap-2 rounded-xl border border-red-500/30 bg-red-950/40 px-3.5 py-2.5 text-xs text-red-200"
              role="alert"
            >
              <svg
                className="h-4 w-4 shrink-0 text-red-400"
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
                />
              </svg>
              <span className="flex-1 text-left">{errorMessage}</span>
            </div>
          )}

          {/* Input Form */}
          <div className="mt-6 w-full space-y-4">
            <div className="relative">
              <input
                ref={inputRef}
                type="text"
                value={code}
                onChange={(e) => {
                  setCode(e.target.value.toUpperCase());
                  if (errorMessage) setErrorMessage(null);
                }}
                onKeyDown={handleKeyDown}
                placeholder="e.g. ALEX123"
                disabled={isVerifying}
                autoComplete="off"
                spellCheck={false}
                className="w-full rounded-2xl border border-white/20 bg-[#0B0C15]/90 px-4 py-3.5 text-center font-mono text-base tracking-widest text-white placeholder-gray-500 outline-none transition-all focus:border-purple-500 focus:bg-[#0E101D] focus:shadow-[0_0_25px_rgba(168,85,247,0.35)] disabled:opacity-50"
                aria-label="Enter promo code"
              />
            </div>

            {/* Verify Button */}
            <button
              type="button"
              onClick={() => void handleVerify()}
              disabled={isVerifying || !code.trim()}
              className="group relative flex w-full items-center justify-center gap-2 rounded-2xl bg-gradient-to-r from-blue-600 via-indigo-600 to-purple-600 px-5 py-3.5 text-sm font-semibold text-white shadow-[0_0_25px_rgba(99,102,241,0.4)] transition-all hover:from-blue-500 hover:via-indigo-500 hover:to-purple-500 hover:shadow-[0_0_35px_rgba(147,51,234,0.6)] active:scale-[0.98] disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:shadow-none"
            >
              {isVerifying ? (
                <>
                  <svg
                    className="h-4 w-4 animate-spin text-white"
                    viewBox="0 0 24 24"
                    fill="none"
                  >
                    <circle
                      className="opacity-25"
                      cx="12"
                      cy="12"
                      r="10"
                      stroke="currentColor"
                      strokeWidth="4"
                    />
                    <path
                      className="opacity-75"
                      fill="currentColor"
                      d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
                    />
                  </svg>
                  <span>Verifying Code...</span>
                </>
              ) : (
                <>
                  <span>Verify Code</span>
                  <span className="transition-transform group-hover:translate-x-0.5">→</span>
                </>
              )}
            </button>
          </div>

          {/* Quick Demo Code Test Helpers */}
          <div className="mt-6 w-full border-t border-white/10 pt-4">
            <p className="text-[11px] font-medium uppercase tracking-wider text-gray-500">
              Quick test codes:
            </p>
            <div className="mt-2 flex flex-wrap justify-center gap-2">
              <button
                type="button"
                onClick={() => handleQuickFill("ALEX123")}
                disabled={isVerifying}
                className="rounded-lg border border-purple-500/30 bg-purple-950/20 px-2.5 py-1 font-mono text-xs text-purple-300 transition hover:border-purple-400 hover:bg-purple-900/40"
              >
                ALEX123
              </button>
            </div>
          </div>

          {/* Security & anti-tamper footer badge */}
          <div className="mt-4 flex items-center justify-center gap-1.5 text-[10px] text-gray-500">
            <svg
              className="h-3.5 w-3.5 text-emerald-400/80"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z"
              />
            </svg>
            <span>Anti-Tamper Security Protected Backend</span>
          </div>
        </div>
      </div>
    </div>
  );
}
