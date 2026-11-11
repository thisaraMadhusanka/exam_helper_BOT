"use client";

import { useState, useEffect, useCallback, useMemo } from "react";
import {
  api,
  type PromoCodeItem,
  type PromoStats,
  type AdminPromoCreateRequest,
} from "../lib/api";

interface AdminPromoManagerProps {
  adminToken: string;
}

export function AdminPromoManager({ adminToken }: AdminPromoManagerProps) {
  const [codes, setCodes] = useState<PromoCodeItem[]>([]);
  const [stats, setStats] = useState<PromoStats | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [statusMessage, setStatusMessage] = useState<{
    type: "success" | "error";
    text: string;
  } | null>(null);

  // Form state
  const [isFormOpen, setIsFormOpen] = useState(false);
  const [codeType, setCodeType] = useState<"custom" | "auto">("custom");
  const [customCode, setCustomCode] = useState("");
  const [prefix, setPrefix] = useState("REF");
  const [label, setLabel] = useState("");
  const [maxUses, setMaxUses] = useState<string>("");
  const [isSubmitting, setIsSubmitting] = useState(false);

  // Search & filter
  const [searchQuery, setSearchQuery] = useState("");
  const [filterActive, setFilterActive] = useState<"all" | "active" | "inactive">("all");

  // Copy feedback state: codeId -> timeout
  const [copiedId, setCopiedId] = useState<string | null>(null);
  const [copiedShareId, setCopiedShareId] = useState<string | null>(null);
  const [copiedMaster, setCopiedMaster] = useState(false);

  // Load promo codes
  const loadCodes = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const data = await api.getAdminPromoCodes(adminToken);
      setCodes(data.codes);
      setStats(data.stats);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load promo codes.");
    } finally {
      setIsLoading(false);
    }
  }, [adminToken]);

  useEffect(() => {
    void loadCodes();
  }, [loadCodes]);

  // Handle create
  const handleCreateCode = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsSubmitting(true);
    setStatusMessage(null);

    const payload: AdminPromoCreateRequest = {
      label: label.trim() || undefined,
      max_uses: maxUses ? parseInt(maxUses, 10) : undefined,
    };

    if (codeType === "custom") {
      const clean = customCode.trim().toUpperCase();
      if (!clean) {
        setStatusMessage({ type: "error", text: "Please enter a custom promo code." });
        setIsSubmitting(false);
        return;
      }
      payload.code = clean;
    } else {
      payload.prefix = prefix.trim().toUpperCase() || "REF";
    }

    try {
      const created = await api.createAdminPromoCode(adminToken, payload);
      setStatusMessage({
        type: "success",
        text: `Promo code "${created.code}" created successfully!`,
      });
      setCustomCode("");
      setLabel("");
      setMaxUses("");
      setIsFormOpen(false);
      await loadCodes();
    } catch (err) {
      setStatusMessage({
        type: "error",
        text: err instanceof Error ? err.message : "Failed to create promo code.",
      });
    } finally {
      setIsSubmitting(false);
    }
  };

  // Toggle active status
  const handleToggleStatus = async (item: PromoCodeItem) => {
    try {
      await api.toggleAdminPromoCode(adminToken, item.id);
      setStatusMessage({
        type: "success",
        text: `Promo code "${item.code}" ${item.is_active ? "deactivated" : "activated"}.`,
      });
      await loadCodes();
    } catch (err) {
      setStatusMessage({
        type: "error",
        text: err instanceof Error ? err.message : "Failed to toggle status.",
      });
    }
  };

  // Delete code
  const handleDeleteCode = async (item: PromoCodeItem) => {
    if (!confirm(`Are you sure you want to delete promo code "${item.code}"?`)) {
      return;
    }
    try {
      await api.deleteAdminPromoCode(adminToken, item.id);
      setStatusMessage({
        type: "success",
        text: `Promo code "${item.code}" has been deleted.`,
      });
      await loadCodes();
    } catch (err) {
      setStatusMessage({
        type: "error",
        text: err instanceof Error ? err.message : "Failed to delete promo code.",
      });
    }
  };

  // Copy code to clipboard
  const handleCopyCode = async (code: string, id: string) => {
    try {
      await navigator.clipboard.writeText(code);
      setCopiedId(id);
      setTimeout(() => setCopiedId(null), 2500);
    } catch {
      // Fallback
    }
  };

  // Copy ready-to-share message
  const handleCopyShareMessage = async (code: string, id: string) => {
    const origin = typeof window !== "undefined" ? window.location.origin : "";
    const msg = `Here is your access code for Ruixen AI Tutor: ${code}\nEnter this code at ${origin} to unlock the AI tutor chat.`;
    try {
      await navigator.clipboard.writeText(msg);
      setCopiedShareId(id);
      setTimeout(() => setCopiedShareId(null), 2500);
    } catch {
      // Fallback
    }
  };

  // Copy Master Admin code
  const handleCopyMasterCode = async () => {
    try {
      await navigator.clipboard.writeText("ADMIN-TM-NEW");
      setCopiedMaster(true);
      setTimeout(() => setCopiedMaster(false), 2500);
    } catch {
      // Fallback
    }
  };

  // Filtered list
  const filteredCodes = useMemo(() => {
    return codes.filter((c) => {
      const q = searchQuery.toLowerCase().trim();
      const matchesSearch =
        !q ||
        c.code.toLowerCase().includes(q) ||
        (c.label && c.label.toLowerCase().includes(q));

      if (!matchesSearch) return false;

      if (filterActive === "active") return c.is_active;
      if (filterActive === "inactive") return !c.is_active;
      return true;
    });
  }, [codes, searchQuery, filterActive]);

  return (
    <div className="space-y-6">
      {/* Master Admin Code Card */}
      <div className="relative overflow-hidden rounded-2xl border border-amber-500/30 bg-gradient-to-r from-amber-950/30 via-[#18151D] to-[#121320] p-5 shadow-xl">
        <div className="absolute right-0 top-0 h-full w-1/3 bg-gradient-to-l from-amber-500/5 to-transparent pointer-events-none" />
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div className="space-y-1">
            <div className="flex items-center gap-2">
              <span className="inline-flex items-center gap-1 rounded-md bg-amber-500/20 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider text-amber-300 border border-amber-500/30">
                ⭐ Master Admin Access Code
              </span>
              <span className="text-[11px] text-gray-400">Default System Pass</span>
            </div>
            <p className="text-sm text-gray-300">
              The permanent master code with full administrative bypass and unlimited chat access:
            </p>
            <div className="flex items-center gap-2 pt-1">
              <code className="rounded-lg bg-black/60 px-3 py-1 font-mono text-base font-bold tracking-widest text-amber-300 border border-amber-500/40">
                ADMIN-TM-NEW
              </code>
              <button
                type="button"
                onClick={handleCopyMasterCode}
                className="inline-flex items-center gap-1.5 rounded-lg border border-amber-500/30 bg-amber-950/40 px-3 py-1.5 text-xs font-medium text-amber-200 transition hover:bg-amber-900/50"
              >
                {copiedMaster ? (
                  <>
                    <span className="text-emerald-400">✓</span>
                    <span>Copied!</span>
                  </>
                ) : (
                  <>
                    <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth={2}
                        d="M8 5H6a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2v-1M8 5a2 2 0 002 2h2a2 2 0 002-2M8 5a2 2 0 012-2h2a2 2 0 012 2m0 0h2a2 2 0 012 2v3m2 4H10m0 0l3-3m-3 3l3 3"
                      />
                    </svg>
                    <span>Copy Master Code</span>
                  </>
                )}
              </button>
            </div>
          </div>
          <div className="rounded-xl border border-white/10 bg-black/30 p-3 text-xs text-gray-400 max-w-sm">
            <p className="font-semibold text-gray-200 mb-1">Where to use ADMIN-TM-NEW:</p>
            <ul className="list-disc list-inside space-y-0.5 text-[11px]">
              <li>On the chat page popup: unlocks full chat & admin mode</li>
              <li>At <span className="font-mono text-purple-300">/login</span>: direct admin authentication</li>
              <li>Admin only can view and share student codes below</li>
            </ul>
          </div>
        </div>
      </div>

      {/* Stats Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
        <div className="rounded-xl border border-white/10 bg-[#121320] p-4 flex items-center justify-between">
          <div>
            <p className="text-[11px] font-medium uppercase tracking-wider text-gray-400">
              Total Student Codes
            </p>
            <p className="mt-1 text-2xl font-bold text-white">{stats?.total_codes ?? codes.length}</p>
          </div>
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-purple-500/10 text-purple-400 border border-purple-500/20 text-lg">
            🎟️
          </div>
        </div>

        <div className="rounded-xl border border-white/10 bg-[#121320] p-4 flex items-center justify-between">
          <div>
            <p className="text-[11px] font-medium uppercase tracking-wider text-gray-400">
              Active Codes
            </p>
            <p className="mt-1 text-2xl font-bold text-emerald-400">
              {stats?.active_codes ?? codes.filter((c) => c.is_active).length}
            </p>
          </div>
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 text-lg">
            ✅
          </div>
        </div>

        <div className="rounded-xl border border-white/10 bg-[#121320] p-4 flex items-center justify-between">
          <div>
            <p className="text-[11px] font-medium uppercase tracking-wider text-gray-400">
              Total Redemptions
            </p>
            <p className="mt-1 text-2xl font-bold text-indigo-400">
              {stats?.total_redemptions ?? codes.reduce((acc, c) => acc + (c.used_count || 0), 0)}
            </p>
          </div>
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-indigo-500/10 text-indigo-400 border border-indigo-500/20 text-lg">
            📊
          </div>
        </div>
      </div>

      {/* Status Alert */}
      {statusMessage && (
        <div
          className={`flex items-center justify-between rounded-xl border p-3.5 text-xs transition-all ${
            statusMessage.type === "success"
              ? "border-green-500/30 bg-green-950/40 text-green-300"
              : "border-red-500/30 bg-red-950/40 text-red-300"
          }`}
        >
          <div className="flex items-center gap-2">
            <span>{statusMessage.type === "success" ? "✓" : "⚠"}</span>
            <span>{statusMessage.text}</span>
          </div>
          <button
            type="button"
            onClick={() => setStatusMessage(null)}
            className="text-gray-400 hover:text-white"
          >
            ✕
          </button>
        </div>
      )}

      {/* Create Promo Code Accordion */}
      <div className="rounded-2xl border border-white/10 bg-[#121320] p-4 sm:p-5 shadow-lg">
        <div className="flex items-center justify-between">
          <button
            type="button"
            onClick={() => setIsFormOpen(!isFormOpen)}
            className="flex items-center gap-2 text-sm font-semibold text-gray-200 hover:text-white transition"
          >
            <div className="flex h-6 w-6 items-center justify-center rounded-md bg-purple-600/20 text-xs text-purple-400">
              {isFormOpen ? "−" : "+"}
            </div>
            <span>Create New Promo / Access Code</span>
            <span className="hidden sm:inline text-[11px] font-normal text-gray-400">
              (Generate custom or random access codes for students)
            </span>
          </button>
          <button
            type="button"
            onClick={() => setIsFormOpen(!isFormOpen)}
            className="text-xs text-purple-400 hover:text-purple-300 transition"
          >
            {isFormOpen ? "Close Form" : "Create Code"}
          </button>
        </div>

        {isFormOpen && (
          <form onSubmit={handleCreateCode} className="mt-4 border-t border-white/10 pt-4 space-y-4">
            <div className="flex items-center gap-4 text-xs">
              <span className="text-gray-400 font-medium">Code Generation Type:</span>
              <label className="flex items-center gap-1.5 cursor-pointer text-gray-200">
                <input
                  type="radio"
                  name="codeType"
                  value="custom"
                  checked={codeType === "custom"}
                  onChange={() => setCodeType("custom")}
                  className="accent-purple-500"
                />
                <span>Custom Code (e.g. ALEX123)</span>
              </label>
              <label className="flex items-center gap-1.5 cursor-pointer text-gray-200">
                <input
                  type="radio"
                  name="codeType"
                  value="auto"
                  checked={codeType === "auto"}
                  onChange={() => setCodeType("auto")}
                  className="accent-purple-500"
                />
                <span>Auto-Generate (e.g. REF-8F3A)</span>
              </label>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              {codeType === "custom" ? (
                <div>
                  <label className="block text-xs font-medium text-gray-400 mb-1">
                    Custom Code *
                  </label>
                  <input
                    type="text"
                    value={customCode}
                    onChange={(e) => setCustomCode(e.target.value.toUpperCase())}
                    placeholder="e.g. ALEX123 or DIPLOMA26"
                    required
                    className="w-full rounded-xl border border-white/10 bg-[#0B0C15] px-3.5 py-2 font-mono text-xs text-white placeholder-gray-500 focus:border-purple-500 focus:outline-none"
                  />
                </div>
              ) : (
                <div>
                  <label className="block text-xs font-medium text-gray-400 mb-1">
                    Prefix (Optional)
                  </label>
                  <input
                    type="text"
                    value={prefix}
                    onChange={(e) => setPrefix(e.target.value.toUpperCase())}
                    placeholder="e.g. REF, STUD, BATCH"
                    maxLength={6}
                    className="w-full rounded-xl border border-white/10 bg-[#0B0C15] px-3.5 py-2 font-mono text-xs text-white placeholder-gray-500 focus:border-purple-500 focus:outline-none"
                  />
                </div>
              )}

              <div>
                <label className="block text-xs font-medium text-gray-400 mb-1">
                  Student / Purpose Label
                </label>
                <input
                  type="text"
                  value={label}
                  onChange={(e) => setLabel(e.target.value)}
                  placeholder="e.g. Alex Student Pass, Fall Semester"
                  className="w-full rounded-xl border border-white/10 bg-[#0B0C15] px-3.5 py-2 text-xs text-white placeholder-gray-500 focus:border-purple-500 focus:outline-none"
                />
              </div>

              <div>
                <label className="block text-xs font-medium text-gray-400 mb-1">
                  Max Redemptions limit
                </label>
                <input
                  type="number"
                  min="1"
                  value={maxUses}
                  onChange={(e) => setMaxUses(e.target.value)}
                  placeholder="Leave empty for unlimited"
                  className="w-full rounded-xl border border-white/10 bg-[#0B0C15] px-3.5 py-2 text-xs text-white placeholder-gray-500 focus:border-purple-500 focus:outline-none"
                />
              </div>
            </div>

            <div className="flex items-center justify-end gap-2 pt-2">
              <button
                type="button"
                onClick={() => setIsFormOpen(false)}
                className="rounded-xl border border-white/10 bg-white/5 px-4 py-2 text-xs font-medium text-gray-300 hover:bg-white/10"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={isSubmitting}
                className="rounded-xl bg-purple-600 px-5 py-2 text-xs font-semibold text-white shadow-md transition hover:bg-purple-500 disabled:opacity-50"
              >
                {isSubmitting ? "Generating..." : "Save & Generate Code"}
              </button>
            </div>
          </form>
        )}
      </div>

      {/* Filter and Search Bar */}
      <div className="flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-3">
        <div className="flex items-center gap-1.5 rounded-xl border border-white/10 bg-[#121320] p-1">
          <button
            type="button"
            onClick={() => setFilterActive("all")}
            className={`rounded-lg px-3 py-1.5 text-xs font-medium transition ${
              filterActive === "all"
                ? "bg-purple-600 text-white shadow-sm"
                : "text-gray-400 hover:text-gray-200"
            }`}
          >
            All ({codes.length})
          </button>
          <button
            type="button"
            onClick={() => setFilterActive("active")}
            className={`rounded-lg px-3 py-1.5 text-xs font-medium transition ${
              filterActive === "active"
                ? "bg-purple-600 text-white shadow-sm"
                : "text-gray-400 hover:text-gray-200"
            }`}
          >
            Active ({codes.filter((c) => c.is_active).length})
          </button>
          <button
            type="button"
            onClick={() => setFilterActive("inactive")}
            className={`rounded-lg px-3 py-1.5 text-xs font-medium transition ${
              filterActive === "inactive"
                ? "bg-purple-600 text-white shadow-sm"
                : "text-gray-400 hover:text-gray-200"
            }`}
          >
            Inactive ({codes.filter((c) => !c.is_active).length})
          </button>
        </div>

        <div className="relative flex-1 sm:max-w-xs">
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search code or student label..."
            className="w-full rounded-xl border border-white/10 bg-[#121320] pl-8 pr-8 py-1.5 text-xs text-white placeholder-gray-500 focus:border-purple-500 focus:outline-none"
          />
          <svg
            className="absolute left-2.5 top-2.5 h-3.5 w-3.5 text-gray-500"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
          >
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
          </svg>
          {searchQuery && (
            <button
              type="button"
              onClick={() => setSearchQuery("")}
              className="absolute right-2.5 top-2 text-xs text-gray-400 hover:text-white"
            >
              ✕
            </button>
          )}
        </div>
      </div>

      {/* Promo Codes List */}
      {isLoading ? (
        <div className="rounded-2xl border border-white/10 bg-[#121320] p-8 text-center text-xs text-gray-400">
          Loading promo codes...
        </div>
      ) : error ? (
        <div className="rounded-2xl border border-red-500/30 bg-red-950/40 p-5 text-xs text-red-300">
          <p>{error}</p>
          <button
            type="button"
            onClick={() => void loadCodes()}
            className="mt-2 rounded-lg bg-white/10 px-3 py-1.5 text-xs font-medium text-white hover:bg-white/15"
          >
            Retry
          </button>
        </div>
      ) : filteredCodes.length === 0 ? (
        <div className="rounded-2xl border border-white/10 bg-[#121320] p-8 text-center text-xs text-gray-400">
          <p>No promo codes found matching your criteria.</p>
          <button
            type="button"
            onClick={() => setIsFormOpen(true)}
            className="mt-3 inline-block rounded-xl bg-purple-600 px-4 py-2 text-xs font-semibold text-white hover:bg-purple-500"
          >
            Create Your First Code
          </button>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {filteredCodes.map((item) => {
            const isCopied = copiedId === item.id;
            const isShareCopied = copiedShareId === item.id;
            const isAtLimit =
              item.max_uses !== null &&
              item.max_uses !== undefined &&
              item.used_count >= item.max_uses;

            return (
              <div
                key={item.id}
                className={`relative flex flex-col justify-between rounded-2xl border p-4 transition-all shadow-md ${
                  !item.is_active
                    ? "border-white/5 bg-[#0F101A]/60 opacity-60"
                    : isAtLimit
                    ? "border-amber-500/30 bg-[#131422]"
                    : "border-white/10 bg-[#131422] hover:border-purple-500/40"
                }`}
              >
                <div>
                  {/* Top Bar: Code & Status */}
                  <div className="flex items-center justify-between gap-2">
                    <span className="font-mono text-base font-bold tracking-wider text-purple-300">
                      {item.code}
                    </span>
                    <div className="flex items-center gap-1.5">
                      {item.is_active ? (
                        isAtLimit ? (
                          <span className="rounded-md border border-amber-500/30 bg-amber-500/20 px-2 py-0.5 text-[10px] font-semibold text-amber-300">
                            Limit Reached
                          </span>
                        ) : (
                          <span className="rounded-md border border-emerald-500/30 bg-emerald-500/20 px-2 py-0.5 text-[10px] font-semibold text-emerald-300">
                            Active
                          </span>
                        )
                      ) : (
                        <span className="rounded-md border border-red-500/30 bg-red-500/20 px-2 py-0.5 text-[10px] font-semibold text-red-300">
                          Inactive
                        </span>
                      )}
                    </div>
                  </div>

                  {/* Label / Student Note */}
                  <p className="mt-1.5 text-xs font-medium text-gray-200 line-clamp-1">
                    {item.label || "General Access Code"}
                  </p>

                  {/* Usage & Date details */}
                  <div className="mt-3 space-y-1 text-[11px] text-gray-400 border-t border-white/5 pt-2.5">
                    <div className="flex items-center justify-between">
                      <span>Redemptions:</span>
                      <span className="font-mono font-semibold text-gray-300">
                        {item.used_count} / {item.max_uses ? `${item.max_uses} max` : "∞ Unlimited"}
                      </span>
                    </div>
                    {item.last_used_at && (
                      <div className="flex items-center justify-between">
                        <span>Last used:</span>
                        <span className="text-[10px] text-gray-400">
                          {new Date(item.last_used_at).toLocaleDateString()}
                        </span>
                      </div>
                    )}
                    <div className="flex items-center justify-between">
                      <span>Created:</span>
                      <span className="text-[10px] text-gray-500">
                        {new Date(item.created_at).toLocaleDateString()}
                      </span>
                    </div>
                  </div>
                </div>

                {/* Bottom Actions: Copy, Share, Toggle, Delete */}
                <div className="mt-4 border-t border-white/10 pt-3 flex flex-col gap-2">
                  <div className="grid grid-cols-2 gap-2">
                    {/* Copy Code Button */}
                    <button
                      type="button"
                      onClick={() => void handleCopyCode(item.code, item.id)}
                      className="flex items-center justify-center gap-1.5 rounded-lg border border-purple-500/30 bg-purple-950/30 px-2.5 py-1.5 text-xs font-medium text-purple-200 transition hover:bg-purple-900/50"
                      title="Copy promo code"
                    >
                      {isCopied ? (
                        <>
                          <span className="text-emerald-400">✓</span>
                          <span>Copied!</span>
                        </>
                      ) : (
                        <>
                          <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 5H6a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2v-1M8 5a2 2 0 002 2h2a2 2 0 002-2M8 5a2 2 0 012-2h2a2 2 0 012 2" />
                          </svg>
                          <span>Copy Code</span>
                        </>
                      )}
                    </button>

                    {/* Share Message Button */}
                    <button
                      type="button"
                      onClick={() => void handleCopyShareMessage(item.code, item.id)}
                      className="flex items-center justify-center gap-1.5 rounded-lg border border-indigo-500/30 bg-indigo-950/30 px-2.5 py-1.5 text-xs font-medium text-indigo-200 transition hover:bg-indigo-900/50"
                      title="Copy full invite message for student"
                    >
                      {isShareCopied ? (
                        <>
                          <span className="text-emerald-400">✓</span>
                          <span>Copied Msg!</span>
                        </>
                      ) : (
                        <>
                          <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8.684 13.342C8.886 12.938 9 12.482 9 12c0-.482-.114-.938-.316-1.342m0 2.684a3 3 0 110-2.684m0 2.684l6.632 3.316m-6.632-6l6.632-3.316m0 0a3 3 0 105.367-2.684 3 3 0 00-5.367 2.684zm0 9.316a3 3 0 105.368 2.684 3 3 0 00-5.368-2.684z" />
                          </svg>
                          <span>Share Invite</span>
                        </>
                      )}
                    </button>
                  </div>

                  <div className="flex items-center justify-between pt-1">
                    {/* Toggle Active Button */}
                    <button
                      type="button"
                      onClick={() => void handleToggleStatus(item)}
                      className={`text-[11px] font-medium transition hover:underline ${
                        item.is_active ? "text-amber-400" : "text-emerald-400"
                      }`}
                    >
                      {item.is_active ? "Disable Code" : "Enable Code"}
                    </button>

                    {/* Delete Button */}
                    <button
                      type="button"
                      onClick={() => void handleDeleteCode(item)}
                      className="text-[11px] font-medium text-red-400 hover:text-red-300 hover:underline"
                    >
                      Delete
                    </button>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
