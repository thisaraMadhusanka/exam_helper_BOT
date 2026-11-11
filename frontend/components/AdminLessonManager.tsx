"use client";

import { useState, useRef, useMemo, useEffect, useCallback } from "react";
import {
  api,
  type KnowledgeDocument,
  type Lesson,
  type LessonDocument,
} from "../lib/api";
import { AdminPromoManager } from "./AdminPromoManager";

interface AdminLessonManagerProps {
  adminToken: string;
  lessons: Lesson[];
  documents?: KnowledgeDocument[];
  onLessonsUpdated: () => void;
  onLogout: () => void;
}

export function AdminLessonManager({
  adminToken,
  lessons,
  documents = [],
  onLessonsUpdated,
  onLogout,
}: AdminLessonManagerProps) {
  const [newTitle, setNewTitle] = useState("");
  const [newDescription, setNewDescription] = useState("");
  const [isCreating, setIsCreating] = useState(false);
  const [isCreateOpen, setIsCreateOpen] = useState(false);
  const [uploadingLessonId, setUploadingLessonId] = useState<string | null>(null);
  const [uploadProgress, setUploadProgress] = useState<number>(0);
  const [deletingLessonId, setDeletingLessonId] = useState<string | null>(null);
  const [deletingDocumentId, setDeletingDocumentId] = useState<string | null>(null);
  const [assigningDocId, setAssigningDocId] = useState<string | null>(null);
  const [statusMessage, setStatusMessage] = useState<{ type: "success" | "error"; text: string } | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [activeTab, setActiveTab] = useState<"all" | "lessons" | "general" | "promos">("all");
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [targetLessonForUpload, setTargetLessonForUpload] = useState<string | null>(null);

  // Helper to extract documents for a lesson (supporting multi-doc and legacy single-doc shapes)
  const getLessonDocuments = (lesson: Lesson): LessonDocument[] => {
    if (lesson.documents && lesson.documents.length > 0) {
      return lesson.documents;
    }
    if (lesson.document_id) {
      return [
        {
          document_id: lesson.document_id,
          pdf_name: lesson.pdf_name || "document.pdf",
          pages_count: lesson.pages_count || 0,
          chunks_count: lesson.chunks_count || 0,
        },
      ];
    }
    return [];
  };

  // Map of document_id to workspace_id for accurate deletion
  const docWorkspaceMap = useMemo(() => {
    const map = new Map<string, string>();
    for (const doc of documents) {
      map.set(String(doc.document_id), doc.workspace_id);
    }
    return map;
  }, [documents]);

  // Set of all document IDs that are attached to at least one lesson
  const attachedDocIds = useMemo(() => {
    const set = new Set<string>();
    for (const lesson of lessons) {
      for (const doc of getLessonDocuments(lesson)) {
        if (doc.document_id) {
          set.add(String(doc.document_id));
        }
      }
    }
    return set;
  }, [lessons]);

  // General Knowledge / Unassigned documents
  const unassignedDocuments = useMemo(() => {
    return documents.filter((doc) => !attachedDocIds.has(String(doc.document_id)));
  }, [documents, attachedDocIds]);

  // Stats calculation
  const totalChunks = useMemo(() => {
    return documents.reduce((acc, doc) => acc + (doc.chunks_count || 0), 0);
  }, [documents]);

  const handleCreateLesson = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newTitle.trim()) return;

    setIsCreating(true);
    setStatusMessage(null);

    try {
      await api.createLesson(adminToken, newTitle.trim(), newDescription.trim());
      setNewTitle("");
      setNewDescription("");
      setIsCreateOpen(false);
      setStatusMessage({ type: "success", text: "Lesson created successfully!" });
      onLessonsUpdated();
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Failed to create lesson";
      setStatusMessage({ type: "error", text: msg });
    } finally {
      setIsCreating(false);
    }
  };

  const handleTriggerUpload = (target: string) => {
    setTargetLessonForUpload(target);
    if (fileInputRef.current) {
      fileInputRef.current.value = "";
      fileInputRef.current.click();
    }
  };

  const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files ?? []);
    const target = targetLessonForUpload;
    if (!files.length || !target) return;

    const invalidFile = files.find(
      (file) =>
        (file.type !== "application/pdf" && !file.name.toLowerCase().endsWith(".pdf")) ||
        file.size > 20 * 1024 * 1024
    );
    if (invalidFile) {
      setStatusMessage({
        type: "error",
        text:
          invalidFile.size > 20 * 1024 * 1024
            ? `${invalidFile.name} exceeds the 20MB limit`
            : `${invalidFile.name} is not a valid PDF`,
      });
      return;
    }

    setUploadingLessonId(target);
    setUploadProgress(15);
    setStatusMessage(null);

    const progressInterval = setInterval(() => {
      setUploadProgress((prev) => Math.min(prev + 12, 90));
    }, 250);

    try {
      const completedFiles: string[] = [];
      for (let index = 0; index < files.length; index++) {
        const file = files[index];
        if (target === "direct") {
          await api.adminDirectUpload(adminToken, file);
        } else {
          await api.uploadLessonPdf(adminToken, target, file);
        }
        completedFiles.push(file.name);
        setUploadProgress(15 + Math.round(((index + 1) / files.length) * 80));
      }
      clearInterval(progressInterval);
      setUploadProgress(100);
      setStatusMessage({
        type: "success",
        text:
          target === "direct"
            ? `${completedFiles.length} PDF${completedFiles.length === 1 ? "" : "s"} added to General Knowledge Base.`
            : `${completedFiles.length} PDF${completedFiles.length === 1 ? "" : "s"} added to the lesson.`,
      });
      onLessonsUpdated();
    } catch (err) {
      clearInterval(progressInterval);
      const msg = err instanceof Error ? err.message : "Failed to upload and process PDF";
      setStatusMessage({ type: "error", text: msg });
    } finally {
      setTimeout(() => {
        setUploadingLessonId(null);
        setUploadProgress(0);
        setTargetLessonForUpload(null);
      }, 500);
    }
  };

  /**
   * Delete a PDF completely from DB and vector storage,
   * also detaching it from any lesson it was associated with.
   */
  const handleDeletePdf = async (
    documentId: string,
    pdfName: string,
    workspaceId?: string
  ) => {
    if (
      !confirm(
        `Permanently delete "${pdfName}"?\n\nThis will remove this PDF and all its vector embeddings and chunks from the database permanently.`
      )
    ) {
      return;
    }

    setDeletingDocumentId(documentId);
    setStatusMessage(null);

    const wsId = workspaceId || docWorkspaceMap.get(String(documentId));

    try {
      const res = await api.adminDeleteDocument(adminToken, documentId, wsId);
      setStatusMessage({
        type: "success",
        text: `"${pdfName}" deleted permanently from the database (${res.chunks_deleted || 0} chunks removed).`,
      });
      onLessonsUpdated();
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Failed to delete PDF from database";
      setStatusMessage({ type: "error", text: msg });
    } finally {
      setDeletingDocumentId(null);
    }
  };

  const handleAssignToLesson = async (lessonId: string, documentId: string, pdfName: string) => {
    if (!lessonId) return;
    setStatusMessage(null);
    try {
      await api.assignDocumentToLesson(adminToken, lessonId, documentId);
      setStatusMessage({
        type: "success",
        text: `"${pdfName}" assigned to lesson successfully.`,
      });
      setAssigningDocId(null);
      onLessonsUpdated();
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Failed to assign PDF to lesson";
      setStatusMessage({ type: "error", text: msg });
    }
  };

  const handleDeleteLesson = async (lessonId: string, title: string) => {
    if (
      !confirm(
        `Are you sure you want to delete lesson "${title}" and all its associated knowledge base chunks?`
      )
    ) {
      return;
    }

    setDeletingLessonId(lessonId);
    try {
      await api.deleteLesson(adminToken, lessonId);
      setStatusMessage({ type: "success", text: `Lesson "${title}" deleted.` });
      onLessonsUpdated();
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Failed to delete lesson";
      setStatusMessage({ type: "error", text: msg });
    } finally {
      setDeletingLessonId(null);
    }
  };

  // Filter helper based on search query
  const matchesSearch = (name: string) => {
    if (!searchQuery.trim()) return true;
    return name.toLowerCase().includes(searchQuery.toLowerCase().trim());
  };

  return (
    <div className="space-y-5 text-gray-100 max-w-7xl mx-auto pb-16">
      {/* Hidden file input for uploads */}
      <input
        type="file"
        ref={fileInputRef}
        onChange={handleFileChange}
        accept="application/pdf,.pdf"
        multiple
        className="hidden"
      />

      {/* Top Banner */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between p-4 sm:p-5 bg-[#121320] border border-white/10 rounded-2xl shadow-xl gap-4">
        <div>
          <div className="flex items-center gap-2">
            <span className="px-2.5 py-0.5 text-[11px] font-bold bg-purple-600/30 text-purple-300 border border-purple-500/30 rounded-full tracking-wide">
              ADMIN CONTROL
            </span>
            <h2 className="text-xl font-bold text-white tracking-tight">Knowledge Base & Lessons</h2>
          </div>
          <p className="text-xs text-gray-400 mt-1">
            Manage course lessons and indexed PDFs. All PDFs are separated by lesson name or general knowledge.
          </p>
        </div>
        <div className="flex items-center gap-2 w-full sm:w-auto justify-end">
          <button
            onClick={() => handleTriggerUpload("direct")}
            disabled={uploadingLessonId === "direct"}
            className="px-3.5 py-2 bg-indigo-600 hover:bg-indigo-500 text-white rounded-xl text-xs font-medium transition shadow-md flex items-center gap-1.5 shrink-0 disabled:opacity-50"
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
            </svg>
            <span>{uploadingLessonId === "direct" ? `Uploading (${uploadProgress}%)` : "Direct Upload PDF"}</span>
          </button>

          <button
            onClick={onLogout}
            className="px-3 py-2 bg-white/5 hover:bg-white/10 text-gray-300 rounded-xl text-xs font-medium transition border border-white/10 shrink-0"
          >
            Logout
          </button>
        </div>
      </div>

      {/* Quick Dashboard Stats Bar */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <div className="p-3.5 bg-[#121320]/90 border border-white/10 rounded-xl flex items-center justify-between">
          <div>
            <p className="text-[11px] font-medium text-gray-400 uppercase tracking-wider">Lessons</p>
            <p className="text-lg font-bold text-white mt-0.5">{lessons.length}</p>
          </div>
          <div className="w-8 h-8 rounded-lg bg-purple-500/10 border border-purple-500/20 flex items-center justify-center text-purple-400 text-sm">
            📚
          </div>
        </div>

        <div className="p-3.5 bg-[#121320]/90 border border-white/10 rounded-xl flex items-center justify-between">
          <div>
            <p className="text-[11px] font-medium text-gray-400 uppercase tracking-wider">Total PDFs</p>
            <p className="text-lg font-bold text-white mt-0.5">{documents.length}</p>
          </div>
          <div className="w-8 h-8 rounded-lg bg-indigo-500/10 border border-indigo-500/20 flex items-center justify-center text-indigo-400 text-sm">
            📄
          </div>
        </div>

        <div className="p-3.5 bg-[#121320]/90 border border-white/10 rounded-xl flex items-center justify-between">
          <div>
            <p className="text-[11px] font-medium text-gray-400 uppercase tracking-wider">Vector Chunks</p>
            <p className="text-lg font-bold text-white mt-0.5">{totalChunks}</p>
          </div>
          <div className="w-8 h-8 rounded-lg bg-emerald-500/10 border border-emerald-500/20 flex items-center justify-center text-emerald-400 text-sm">
            🧩
          </div>
        </div>

        <div className="p-3.5 bg-[#121320]/90 border border-white/10 rounded-xl flex items-center justify-between">
          <div>
            <p className="text-[11px] font-medium text-gray-400 uppercase tracking-wider">General PDFs</p>
            <p className="text-lg font-bold text-white mt-0.5">{unassignedDocuments.length}</p>
          </div>
          <div className="w-8 h-8 rounded-lg bg-amber-500/10 border border-amber-500/20 flex items-center justify-center text-amber-400 text-sm">
            🌐
          </div>
        </div>
      </div>

      {/* Status Alert */}
      {statusMessage && (
        <div
          className={`p-3.5 rounded-xl text-xs border flex items-center justify-between transition-all ${
            statusMessage.type === "success"
              ? "bg-green-950/40 text-green-300 border-green-500/30"
              : "bg-red-950/40 text-red-300 border-red-500/30"
          }`}
        >
          <div className="flex items-center gap-2">
            <span>{statusMessage.type === "success" ? "✓" : "⚠"}</span>
            <span>{statusMessage.text}</span>
          </div>
          <button
            onClick={() => setStatusMessage(null)}
            className="text-gray-400 hover:text-white ml-2 text-sm"
          >
            ✕
          </button>
        </div>
      )}

      {/* Add Course Lesson Accordion/Form */}
      {activeTab !== "promos" && (
        <div className="p-4 sm:p-5 bg-[#121320] rounded-2xl border border-white/10 shadow-lg">
          <div className="flex items-center justify-between">
            <button
              type="button"
              onClick={() => setIsCreateOpen(!isCreateOpen)}
              className="flex items-center gap-2 text-sm font-semibold text-gray-200 hover:text-white transition"
            >
              <div className="w-6 h-6 rounded-md bg-purple-600/20 text-purple-400 flex items-center justify-center text-xs">
                {isCreateOpen ? "−" : "+"}
              </div>
              <span>Add Course Lesson</span>
              <span className="text-[11px] font-normal text-gray-400">
                (Create named folders/categories for your PDFs)
              </span>
            </button>
            <button
              type="button"
              onClick={() => setIsCreateOpen(!isCreateOpen)}
              className="text-xs text-purple-400 hover:text-purple-300 transition"
            >
              {isCreateOpen ? "Hide Form" : "Create New"}
            </button>
          </div>

          {isCreateOpen && (
            <form onSubmit={handleCreateLesson} className="mt-4 pt-4 border-t border-white/10 space-y-4">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                  <label className="block text-xs font-medium text-gray-400 mb-1">
                    Lesson Title *
                  </label>
                  <input
                    type="text"
                    value={newTitle}
                    onChange={(e) => setNewTitle(e.target.value)}
                    placeholder="e.g. Lesson 1: Introduction to Data Structures"
                    className="w-full px-3.5 py-2 text-xs border border-white/10 rounded-xl bg-black/40 text-white placeholder-gray-500 focus:outline-none focus:border-purple-500"
                    required
                  />
                </div>
                <div>
                  <label className="block text-xs font-medium text-gray-400 mb-1">
                    Description / Topics (Optional)
                  </label>
                  <input
                    type="text"
                    value={newDescription}
                    onChange={(e) => setNewDescription(e.target.value)}
                    placeholder="e.g. Arrays, Linked Lists, Stacks, Queues"
                    className="w-full px-3.5 py-2 text-xs border border-white/10 rounded-xl bg-black/40 text-white placeholder-gray-500 focus:outline-none focus:border-purple-500"
                  />
                </div>
              </div>
              <div className="flex justify-end gap-2">
                <button
                  type="button"
                  onClick={() => setIsCreateOpen(false)}
                  className="px-3 py-1.5 text-xs text-gray-400 hover:text-white rounded-lg"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={isCreating || !newTitle.trim()}
                  className="px-4 py-2 bg-purple-600 hover:bg-purple-500 text-white rounded-xl text-xs font-medium disabled:opacity-50 transition"
                >
                  {isCreating ? "Creating..." : "Save Lesson"}
                </button>
              </div>
            </form>
          )}
        </div>
      )}

      {/* Filter Tabs & Search Bar */}
      <div className="flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-3 pt-1">
        {/* Filter Pills */}
        <div className="flex items-center gap-1.5 bg-[#121320] p-1 rounded-xl border border-white/10 self-start">
          <button
            onClick={() => setActiveTab("all")}
            className={`px-3 py-1.5 text-xs font-medium rounded-lg transition ${
              activeTab === "all"
                ? "bg-purple-600 text-white shadow-sm"
                : "text-gray-400 hover:text-gray-200"
            }`}
          >
            All Separated ({documents.length})
          </button>
          <button
            onClick={() => setActiveTab("lessons")}
            className={`px-3 py-1.5 text-xs font-medium rounded-lg transition ${
              activeTab === "lessons"
                ? "bg-purple-600 text-white shadow-sm"
                : "text-gray-400 hover:text-gray-200"
            }`}
          >
            By Lessons ({lessons.length})
          </button>
          <button
            onClick={() => setActiveTab("general")}
            className={`px-3 py-1.5 text-xs font-medium rounded-lg transition ${
              activeTab === "general"
                ? "bg-purple-600 text-white shadow-sm"
                : "text-gray-400 hover:text-gray-200"
            }`}
          >
            General Knowledge ({unassignedDocuments.length})
          </button>
          <button
            onClick={() => setActiveTab("promos")}
            className={`px-3 py-1.5 text-xs font-medium rounded-lg transition flex items-center gap-1.5 ${
              activeTab === "promos"
                ? "bg-purple-600 text-white shadow-sm"
                : "text-gray-400 hover:text-gray-200"
            }`}
          >
            <span>🎟️ Promo Codes</span>
          </button>
        </div>

        {/* Quick Search Input */}
        <div className="relative flex-1 sm:max-w-xs">
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search PDFs by filename..."
            className="w-full pl-8 pr-3 py-1.5 text-xs border border-white/10 rounded-xl bg-[#121320] text-white placeholder-gray-500 focus:outline-none focus:border-purple-500"
          />
          <svg
            className="w-3.5 h-3.5 absolute left-2.5 top-2.5 text-gray-500"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
          </svg>
          {searchQuery && (
            <button
              onClick={() => setSearchQuery("")}
              className="absolute right-2.5 top-2 text-xs text-gray-400 hover:text-white"
            >
              ✕
            </button>
          )}
        </div>
      </div>

      {/* ==================================================================== */}
      {/* SECTION 1: COURSE LESSONS & THEIR PDFs (Separated by Lesson Name)     */}
      {/* ==================================================================== */}
      {(activeTab === "all" || activeTab === "lessons") && (
        <section className="space-y-4">
          <div className="flex items-center justify-between border-b border-white/10 pb-2">
            <div>
              <h3 className="text-sm font-semibold text-white flex items-center gap-2">
                <span>📘</span> Course Lessons & Attached PDFs ({lessons.length})
              </h3>
              <p className="text-[11px] text-gray-400">
                PDFs are grouped and separated under each lesson title.
              </p>
            </div>
            {lessons.length === 0 && (
              <button
                onClick={() => setIsCreateOpen(true)}
                className="text-xs text-purple-400 hover:text-purple-300 font-medium"
              >
                + Create Lesson
              </button>
            )}
          </div>

          {lessons.length === 0 ? (
            <div className="p-8 text-center bg-[#121320] rounded-2xl border border-white/10 text-gray-400">
              <p className="text-xs">No course lessons created yet.</p>
              <p className="text-[11px] text-gray-500 mt-1">
                Create a lesson above to organize your PDFs into structured subjects and course modules.
              </p>
            </div>
          ) : (
            <div className="space-y-4">
              {lessons.map((lesson) => {
                const lessonDocs = getLessonDocuments(lesson).filter((d) =>
                  matchesSearch(d.pdf_name)
                );
                const allLessonDocs = getLessonDocuments(lesson);
                const isUploadingThis = uploadingLessonId === lesson.id;
                const isDeletingThis = deletingLessonId === lesson.id;

                return (
                  <div
                    key={lesson.id}
                    className="p-4 sm:p-5 bg-[#121320] rounded-2xl border border-white/10 shadow-md space-y-3"
                  >
                    {/* Lesson Header */}
                    <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2.5 pb-2 border-b border-white/5">
                      <div className="min-w-0">
                        <div className="flex items-center gap-2 flex-wrap">
                          <h4 className="text-sm font-bold text-white tracking-wide truncate">
                            {lesson.title}
                          </h4>
                          <span
                            className={`px-2 py-0.5 rounded-full text-[10px] font-semibold border ${
                              allLessonDocs.length > 0
                                ? "bg-green-500/10 text-green-300 border-green-500/20"
                                : "bg-amber-500/10 text-amber-300 border-amber-500/20"
                            }`}
                          >
                            {allLessonDocs.length} PDF{allLessonDocs.length === 1 ? "" : "s"}
                          </span>
                          <span className="text-[11px] text-gray-400">
                            · {lesson.pages_count || 0} pages · {lesson.chunks_count || 0} chunks
                          </span>
                        </div>
                        {lesson.description && (
                          <p className="text-xs text-gray-400 mt-0.5 truncate">
                            {lesson.description}
                          </p>
                        )}
                      </div>

                      {/* Lesson Action Buttons */}
                      <div className="flex items-center gap-2 shrink-0 self-end sm:self-auto">
                        <button
                          onClick={() => handleTriggerUpload(lesson.id)}
                          disabled={isUploadingThis}
                          className="px-3 py-1.5 text-xs rounded-xl bg-purple-600/20 hover:bg-purple-600/30 text-purple-200 border border-purple-500/30 transition flex items-center gap-1.5 disabled:opacity-50"
                        >
                          <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
                          </svg>
                          <span>{isUploadingThis ? `Uploading (${uploadProgress}%)` : "Add PDF"}</span>
                        </button>

                        <button
                          onClick={() => handleDeleteLesson(lesson.id, lesson.title)}
                          disabled={isDeletingThis}
                          className="px-2.5 py-1.5 text-xs rounded-xl text-red-400 hover:bg-red-500/10 border border-transparent hover:border-red-500/20 transition disabled:opacity-50"
                          title="Delete entire lesson and its chunks"
                        >
                          {isDeletingThis ? "Deleting..." : "Delete Lesson"}
                        </button>
                      </div>
                    </div>

                    {/* Lesson PDFs Grid (3 Columns with controlled Scroll) */}
                    {allLessonDocs.length === 0 ? (
                      <div className="p-4 text-center rounded-xl bg-black/20 border border-white/5 text-gray-500 text-xs">
                        No PDFs attached to this lesson yet. Click{" "}
                        <button
                          onClick={() => handleTriggerUpload(lesson.id)}
                          className="text-purple-400 hover:underline"
                        >
                          + Add PDF
                        </button>{" "}
                        to upload lecture slides or notes.
                      </div>
                    ) : lessonDocs.length === 0 ? (
                      <div className="p-3 text-center text-gray-500 text-xs">
                        No PDFs in this lesson match &quot;{searchQuery}&quot;.
                      </div>
                    ) : (
                      <div className="max-h-[360px] overflow-y-auto pr-1">
                        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
                          {lessonDocs.map((doc) => {
                            const isDeleting = deletingDocumentId === doc.document_id;
                            const wsId = docWorkspaceMap.get(String(doc.document_id)) || lesson.workspace_id;

                            return (
                              <div
                                key={doc.document_id}
                                className="p-3 bg-[#181a2e]/90 hover:bg-[#1c1f36] border border-white/10 hover:border-purple-500/30 rounded-xl transition-all shadow-sm flex flex-col justify-between gap-2.5 group"
                              >
                                <div className="flex items-start gap-2.5 min-w-0">
                                  {/* PDF Badge Icon */}
                                  <div className="w-8 h-8 rounded-lg bg-red-500/15 border border-red-500/30 flex items-center justify-center text-red-400 shrink-0 font-bold text-[10px]">
                                    PDF
                                  </div>

                                  <div className="min-w-0 flex-1">
                                    <p
                                      className="text-xs font-semibold text-white truncate"
                                      title={doc.pdf_name}
                                    >
                                      {doc.pdf_name}
                                    </p>
                                    <p className="text-[11px] text-gray-400 mt-0.5">
                                      {doc.pages_count} pages · {doc.chunks_count} chunks
                                    </p>
                                  </div>
                                </div>

                                <div className="flex items-center justify-between pt-2 border-t border-white/5 text-[11px]">
                                  <span className="text-[10px] text-purple-300/80 bg-purple-500/10 px-2 py-0.5 rounded-md truncate max-w-[120px]">
                                    {lesson.title}
                                  </span>

                                  {/* Delete PDF button */}
                                  <button
                                    type="button"
                                    onClick={() => handleDeletePdf(doc.document_id, doc.pdf_name, wsId)}
                                    disabled={isDeleting}
                                    className="px-2 py-1 text-[11px] text-red-400 hover:text-red-300 hover:bg-red-500/10 rounded-lg transition flex items-center gap-1 disabled:opacity-50"
                                    title={`Delete ${doc.pdf_name} and remove from database`}
                                  >
                                    <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                                    </svg>
                                    <span>{isDeleting ? "Deleting..." : "Delete"}</span>
                                  </button>
                                </div>
                              </div>
                            );
                          })}
                        </div>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </section>
      )}

      {/* ==================================================================== */}
      {/* SECTION 2: GENERAL KNOWLEDGE & STANDALONE PDFs                        */}
      {/* ==================================================================== */}
      {(activeTab === "all" || activeTab === "general") && (
        <section className="p-4 sm:p-5 bg-[#121320] rounded-2xl border border-white/10 shadow-lg space-y-4">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-white/10 pb-3">
            <div>
              <div className="flex items-center gap-2">
                <h3 className="text-sm font-semibold text-white flex items-center gap-2">
                  <span>🌐</span> General Knowledge & Standalone PDFs ({unassignedDocuments.length})
                </h3>
                <span className="text-[10px] bg-white/5 border border-white/10 px-2 py-0.5 rounded-full text-gray-300">
                  Global Searchable
                </span>
              </div>
              <p className="text-[11px] text-gray-400 mt-1">
                PDFs not assigned to a specific course lesson. They are searched globally by all students.
              </p>
            </div>

            <button
              onClick={() => handleTriggerUpload("direct")}
              disabled={uploadingLessonId === "direct"}
              className="px-3.5 py-1.5 bg-indigo-600/30 hover:bg-indigo-600/50 text-indigo-200 border border-indigo-500/30 rounded-xl text-xs font-medium transition flex items-center gap-1.5 shrink-0 self-start sm:self-auto disabled:opacity-50"
            >
              <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
              </svg>
              <span>{uploadingLessonId === "direct" ? `Uploading (${uploadProgress}%)` : "Upload Standalone PDF"}</span>
            </button>
          </div>

          {unassignedDocuments.length === 0 ? (
            <div className="p-6 text-center text-gray-500 text-xs">
              No standalone PDFs. All indexed PDFs are currently organized under course lessons.
            </div>
          ) : (
            (() => {
              const filteredUnassigned = unassignedDocuments.filter((d) =>
                matchesSearch(d.pdf_name)
              );

              if (filteredUnassigned.length === 0) {
                return (
                  <div className="p-4 text-center text-gray-500 text-xs">
                    No general knowledge PDFs match &quot;{searchQuery}&quot;.
                  </div>
                );
              }

              return (
                <div className="max-h-[380px] overflow-y-auto pr-1">
                  {/* 3 Columns Grid */}
                  <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
                    {filteredUnassigned.map((document) => {
                      const isDeleting = deletingDocumentId === document.document_id;
                      const isAssigning = assigningDocId === document.document_id;

                      return (
                        <div
                          key={`${document.workspace_id}:${document.document_id}`}
                          className="p-3 bg-[#181a2e]/90 hover:bg-[#1c1f36] border border-white/10 hover:border-indigo-500/30 rounded-xl transition-all shadow-sm flex flex-col justify-between gap-2.5"
                        >
                          <div className="flex items-start gap-2.5 min-w-0">
                            {/* PDF Badge Icon */}
                            <div className="w-8 h-8 rounded-lg bg-indigo-500/15 border border-indigo-500/30 flex items-center justify-center text-indigo-400 shrink-0 font-bold text-[10px]">
                              PDF
                            </div>

                            <div className="min-w-0 flex-1">
                              <p
                                className="text-xs font-semibold text-white truncate"
                                title={document.pdf_name}
                              >
                                {document.pdf_name}
                              </p>
                              <p className="text-[11px] text-gray-400 mt-0.5">
                                {document.pages_count} pages · {document.chunks_count} chunks
                              </p>
                            </div>
                          </div>

                          {/* Quick Assign Dropdown if active */}
                          {isAssigning && lessons.length > 0 ? (
                            <div className="p-2 bg-black/40 rounded-lg border border-white/10 space-y-2 text-xs">
                              <label className="block text-[10px] text-gray-400">
                                Select Lesson to Assign:
                              </label>
                              <select
                                onChange={(e) => {
                                  if (e.target.value) {
                                    handleAssignToLesson(e.target.value, document.document_id, document.pdf_name);
                                  }
                                }}
                                defaultValue=""
                                className="w-full px-2 py-1 text-xs bg-[#121320] border border-white/20 rounded-md text-white focus:outline-none focus:border-purple-500"
                              >
                                <option value="" disabled>Choose a lesson...</option>
                                {lessons.map((l) => (
                                  <option key={l.id} value={l.id}>{l.title}</option>
                                ))}
                              </select>
                              <div className="flex justify-end">
                                <button
                                  type="button"
                                  onClick={() => setAssigningDocId(null)}
                                  className="text-[10px] text-gray-400 hover:text-white"
                                >
                                  Cancel
                                </button>
                              </div>
                            </div>
                          ) : (
                            <div className="flex items-center justify-between pt-2 border-t border-white/5 text-[11px]">
                              <div className="flex items-center gap-1.5">
                                <span className="px-2 py-0.5 rounded-full text-[10px] bg-white/5 border border-white/10 text-gray-400">
                                  General
                                </span>

                                {/* Quick Assign trigger if lessons exist */}
                                {lessons.length > 0 && (
                                  <button
                                    type="button"
                                    onClick={() => setAssigningDocId(document.document_id)}
                                    className="text-[10px] text-purple-400 hover:text-purple-300 transition"
                                  >
                                    Move to Lesson
                                  </button>
                                )}
                              </div>

                              {/* Delete PDF button */}
                              <button
                                type="button"
                                onClick={() =>
                                  handleDeletePdf(
                                    document.document_id,
                                    document.pdf_name,
                                    document.workspace_id
                                  )
                                }
                                disabled={isDeleting}
                                className="px-2 py-1 text-[11px] text-red-400 hover:text-red-300 hover:bg-red-500/10 rounded-lg transition flex items-center gap-1 disabled:opacity-50"
                                title={`Delete ${document.pdf_name} permanently`}
                              >
                                <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                                </svg>
                                <span>{isDeleting ? "Deleting..." : "Delete"}</span>
                              </button>
                            </div>
                          )}
                        </div>
                      );
                    })}
                  </div>
                </div>
              );
            })()
          )}
        </section>
      )}

      {/* ==================================================================== */}
      {/* SECTION 3: ACCESS PROMO CODES MANAGER                                */}
      {/* ==================================================================== */}
      {activeTab === "promos" && (
        <section className="space-y-4">
          <AdminPromoManager adminToken={adminToken} />
        </section>
      )}
    </div>
  );
}
