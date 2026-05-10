import { useEffect, useState } from 'react';
import { useAtomValue } from 'jotai';
import type { WireProject } from '@kagan/shared-api-client';
import { apiClient } from '@/lib/api/client';
import { projectSwitchVersionAtom } from '@/lib/atoms/board';

export function useActiveProject(): WireProject | null {
  const switchVersion = useAtomValue(projectSwitchVersionAtom);
  const [active, setActive] = useState<WireProject | null>(null);

  useEffect(() => {
    let cancelled = false;
    apiClient
      .getProjects()
      .then((projects) => {
        if (cancelled) return;
        setActive(projects.find((p) => p.active) ?? null);
      })
      .catch(() => {
        if (!cancelled) setActive(null);
      });
    return () => {
      cancelled = true;
    };
  }, [switchVersion]);

  return active;
}
