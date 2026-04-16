import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate } from 'react-router';
import { toast } from 'sonner';
import { useSetAtom } from 'jotai';
import { apiClient } from '@/lib/api/client';
import type { WireTask } from '@/lib/api/types';
import { fetchTasksAtom } from '@/lib/atoms/board';
import { classifyIntent, type ClassifiedIntent } from '@/lib/intent/classify-intent';
import { LiveRegion } from '@/components/a11y/live-region';
import { IntentInput } from '@/components/home/intent-input';
import { IntentPreview } from '@/components/home/intent-preview';
import { RecentActivity } from '@/components/home/recent-activity';

const PREVIEW_MIN_CHARS = 5;
const ANNOUNCE_DEBOUNCE_MS = 300;
const RECENTS_LIMIT = 5;

function greetingFor(date: Date): string {
  const hour = date.getHours();
  if (hour < 5) return 'Still up';
  if (hour < 12) return 'Good morning';
  if (hour < 18) return 'Good afternoon';
  return 'Good evening';
}

function previewDescription(intent: ClassifiedIntent, rawInput: string): string {
  switch (intent.kind) {
    case 'create-task':
      return `Create task: ${intent.extractedFields?.title ?? rawInput}`;
    case 'chat':
      return 'Ask in chat';
    case 'search':
      return `Search tasks for ${rawInput}`;
    case 'navigate-analytics':
      return 'Open analytics';
    case 'navigate-settings':
      return 'Open settings';
    case 'navigate-board':
      return 'Open board';
    case 'navigate-workspace':
      return 'Open workspace';
    case 'unknown':
      return 'Open chat';
  }
}

function sortByRecency(tasks: WireTask[]): WireTask[] {
  return [...tasks].sort((a, b) => {
    const ak = a.last_event_at ?? a.updated_at ?? '';
    const bk = b.last_event_at ?? b.updated_at ?? '';
    return bk.localeCompare(ak);
  });
}

export function HomePage() {
  const navigate = useNavigate();
  const fetchTasks = useSetAtom(fetchTasksAtom);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  const [value, setValue] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [recent, setRecent] = useState<WireTask[]>([]);
  const [recentsLoading, setRecentsLoading] = useState(true);
  const [announcement, setAnnouncement] = useState<string | null>(null);

  const greeting = useMemo(() => greetingFor(new Date()), []);
  const intent = useMemo(() => classifyIntent(value), [value]);
  const previewVisible = value.trim().length >= PREVIEW_MIN_CHARS;

  // Focus the input on mount. Intentionally plain autofocus — this is the
  // single primary affordance on the page, so the aggressive focus is wanted.
  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  // Debounced live-region announcement of the classified intent.
  useEffect(() => {
    if (!previewVisible) {
      setAnnouncement(null);
      return;
    }
    const handle = window.setTimeout(() => {
      setAnnouncement(previewDescription(intent, value));
    }, ANNOUNCE_DEBOUNCE_MS);
    return () => window.clearTimeout(handle);
  }, [intent, value, previewVisible]);

  // Load recent tasks.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const tasks = await apiClient.getTasks();
        if (cancelled) return;
        setRecent(sortByRecency(tasks).slice(0, RECENTS_LIMIT));
      } catch {
        if (!cancelled) setRecent([]);
      } finally {
        if (!cancelled) setRecentsLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const handleSubmit = useCallback(async () => {
    const raw = value.trim();
    if (!raw || submitting) return;

    if (intent.kind === 'create-task') {
      setSubmitting(true);
      try {
        const title = intent.extractedFields?.title ?? raw;
        const task = await apiClient.createTask({ title });
        toast.success('Task created');
        fetchTasks();
        navigate(`/task/${task.id}`);
      } catch (error) {
        toast.error(error instanceof Error ? error.message : 'Failed to create task');
        setSubmitting(false);
      }
      return;
    }

    if (intent.kind === 'search') {
      navigate(`/board?q=${encodeURIComponent(raw)}`);
      return;
    }

    navigate(intent.route);
  }, [value, intent, submitting, navigate, fetchTasks]);

  return (
    <div className="flex min-h-[80vh] w-full flex-col items-center justify-center bg-[color:var(--surface-0)] px-4 py-16 sm:px-6">
      <div className="flex w-full max-w-xl flex-col gap-6">
        <header className="flex flex-col gap-1">
          <h1 className="text-[26px] font-medium leading-tight text-[var(--foreground)]">
            {greeting}
          </h1>
          <p className="text-sm text-[var(--muted-foreground)]">
            What do you want to do?
          </p>
        </header>

        <div className="flex flex-col gap-2">
          <IntentInput
            ref={inputRef}
            value={value}
            onChange={setValue}
            onSubmit={handleSubmit}
            disabled={submitting}
            describedBy={previewVisible ? 'home-intent-preview' : undefined}
          />
          <IntentPreview intent={intent} rawInput={value} visible={previewVisible} />
        </div>

        <RecentActivity tasks={recent} loading={recentsLoading} />
      </div>

      <LiveRegion message={announcement} />
    </div>
  );
}

export const Component = HomePage;
