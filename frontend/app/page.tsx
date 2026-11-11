"use client";

import { useState, useEffect, useCallback } from "react";
import { ChatBox } from "../components/ChatBox";
import { api, type SessionResponse, type Lesson } from "../lib/api";

export default function Home() {
  const [session, setSession] = useState<SessionResponse | null>(null);
  const [lessons, setLessons] = useState<Lesson[]>([]);
  const [selectedLessonId, setSelectedLessonId] = useState<string | null>(null);

  const refreshLessons = useCallback(async () => {
    try {
      const data = await api.getLessons();
      const safeLessons = Array.isArray(data) ? data : [];
      setLessons(safeLessons);
      setSelectedLessonId((selectedId) =>
        selectedId && !safeLessons.some((lesson) => lesson.id === selectedId) ? null : selectedId
      );
    } catch (err) {
      console.warn("Failed to fetch lessons:", err);
      setLessons([]);
    }
  }, []);

  const handleSelectLesson = useCallback((lessonId: string | null) => {
    setSelectedLessonId(lessonId);
  }, []);

  useEffect(() => {
    const init = async () => {
      try {
        setSession(await api.createSession());
      } catch (err) {
        console.warn("Session init warning:", err);
      }

      await refreshLessons();
    };

    void init();
  }, [refreshLessons]);

  return (
    <div className="relative flex h-dvh min-h-0 flex-col overflow-hidden bg-[#07080E] font-sans text-white selection:bg-purple-600 selection:text-white">
      <main className="relative z-10 flex min-h-0 w-full flex-1 flex-col">
        <div className="h-full w-full">
          <ChatBox
            session={session}
            lessons={lessons}
            selectedLessonId={selectedLessonId}
            onSelectLesson={handleSelectLesson}
          />
        </div>
      </main>
    </div>
  );
}
