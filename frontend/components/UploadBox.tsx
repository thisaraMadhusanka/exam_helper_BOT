"use client";

import { useState, useCallback, useRef } from "react";
import { api, type UploadResponse, type SessionResponse } from "../lib/api";

interface UploadBoxProps {
  onUploadComplete: (response: UploadResponse) => void;
  onSessionCreated: (session: SessionResponse) => void;
}

export function UploadBox({ onUploadComplete, onSessionCreated }: UploadBoxProps) {
  const [isUploading, setIsUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [session, setSession] = useState<SessionResponse | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const createSession = useCallback(async () => {
    try {
      const sessionData = await api.createSession();
      setSession(sessionData);
      onSessionCreated(sessionData);
      return sessionData;
    } catch (err) {
      const message = err instanceof Error ? err.message : "Failed to create session";
      setError(message);
      throw err;
    }
  }, [onSessionCreated]);

  const handleFileSelect = useCallback((event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;

    // Validate file type
    if (file.type !== "application/pdf" && !file.name.toLowerCase().endsWith(".pdf")) {
      setError("Please select a PDF file");
      return;
    }

    // Validate file size (20MB)
    if (file.size > 20 * 1024 * 1024) {
      setError("File size must be less than 20MB");
      return;
    }

    uploadFile(file);
  }, []);

  const uploadFile = useCallback(async (file: File) => {
    if (!session) {
      await createSession();
    }

    if (!session) {
      setError("No active session. Please refresh the page.");
      return;
    }

    setIsUploading(true);
    setUploadProgress(0);
    setError(null);

    try {
      // Simulate progress updates
      const progressInterval = setInterval(() => {
        setUploadProgress((prev) => Math.min(prev + 10, 90));
      }, 200);

      const response = await api.uploadPdf(session.access_token, file);

      clearInterval(progressInterval);
      setUploadProgress(100);

      onUploadComplete(response);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Upload failed";
      setError(message);
    } finally {
      setIsUploading(false);
      setTimeout(() => setUploadProgress(0), 1000);
      // Reset file input
      if (fileInputRef.current) {
        fileInputRef.current.value = "";
      }
    }
  }, [session, createSession, onUploadComplete]);

  const handleDragOver = useCallback((event: React.DragEvent) => {
    event.preventDefault();
    event.stopPropagation();
  }, []);

  const handleDrop = useCallback((event: React.DragEvent) => {
    event.preventDefault();
    event.stopPropagation();

    const file = event.dataTransfer.files[0];
    if (file) {
        const syntheticEvent = {
        target: { files: [file] },
          currentTarget: { files: [file] },
          nativeEvent: event.nativeEvent,
          bubbles: true,
          cancelable: true,
          defaultPrevented: false,
          eventPhase: 0,
          isDefaultPrevented: () => false,
          isPropagationStopped: () => false,
          persist: () => {},
          preventDefault: () => {},
          stopPropagation: () => {},
          timeStamp: Date.now(),
          type: "change",
        } as unknown as React.ChangeEvent<HTMLInputElement>;
        handleFileSelect(syntheticEvent);
      }
    }, [handleFileSelect]);

  const triggerFileInput = () => {
    fileInputRef.current?.click();
  };

  return (
    <div className="bg-white dark:bg-gray-800 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700 p-6">
      <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-4">
        Upload PDF
      </h2>

      {!session ? (
        <div className="text-center py-8">
          <button
            onClick={createSession}
            disabled={isUploading}
            className="btn btn-primary w-full max-w-md"
          >
            Create Session & Upload PDF
          </button>
        </div>
      ) : (
        <>
          <div
            className={`border-2 border-dashed rounded-lg p-8 text-center transition-colors ${
              isUploading
                ? "border-primary/50 bg-primary/5"
                : "border-gray-300 dark:border-gray-600 hover:border-primary/50"
            }`}
            onDragOver={handleDragOver}
            onDrop={handleDrop}
          >
            <input
              ref={fileInputRef}
              type="file"
              accept=".pdf,application/pdf"
              onChange={handleFileSelect}
              className="hidden"
              disabled={isUploading}
            />

            <div className="space-y-3">
              <svg
                className="mx-auto h-12 w-12 text-gray-400"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={1.5}
                  d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12"
                />
              </svg>

              <div>
                <p className="text-gray-600 dark:text-gray-400">
                  Drag and drop a PDF file here, or{" "}
                  <button
                    type="button"
                    onClick={triggerFileInput}
                    className="text-primary hover:underline font-medium"
                  >
                    click to select
                  </button>
                </p>
                <p className="text-sm text-gray-500 dark:text-gray-500 mt-1">
                  Max size: 20MB • PDF files only
                </p>
              </div>
            </div>
          </div>

          {isUploading && (
            <div className="mt-4 space-y-2">
              <div className="flex justify-between text-sm">
                <span className="text-gray-600 dark:text-gray-400">Uploading...</span>
                <span className="font-medium">{uploadProgress}%</span>
              </div>
              <div className="h-2 bg-gray-200 dark:bg-gray-700 rounded-full overflow-hidden">
                <div
                  className="h-full bg-primary transition-all duration-300"
                  style={{ width: `${uploadProgress}%` }}
                />
              </div>
            </div>
          )}

          {error && (
            <div className="mt-4 p-3 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg">
              <p className="text-red-600 dark:text-red-400 text-sm">{error}</p>
            </div>
          )}
        </>
      )}
    </div>
  );
}