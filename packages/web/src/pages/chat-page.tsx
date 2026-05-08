import { useEffect } from 'react';
import { useParams, useNavigate } from 'react-router';
import { toast } from 'sonner';
import { apiClient } from '@/lib/api/client';
import { useSessionOverlay } from '@/lib/hooks/use-session-overlay';

export function Component() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const overlay = useSessionOverlay();

  useEffect(() => {
    if (!id) {
      navigate('/workspace');
      return;
    }

    let cancelled = false;

    void (async () => {
      try {
        const response = await apiClient.getSessions();
        if (cancelled) return;
        const session = response.sessions.find(
          (s) => s.id === id || s.chat_session_id === id,
        );
        if (session) {
          overlay.open(session);
        } else {
          toast.error('Session not found');
        }
      } catch (error) {
        if (!cancelled) {
          toast.error(error instanceof Error ? error.message : 'Failed to load session');
        }
      }
      if (!cancelled) {
        navigate('/workspace');
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [id, navigate, overlay]);

  return (
    <div className="flex h-full items-center justify-center px-6 py-10">
      <div className="h-14 w-56 animate-pulse bg-[var(--muted)]" />
    </div>
  );
}
