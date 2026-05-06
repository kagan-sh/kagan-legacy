import { useCallback, useEffect, useMemo, useState } from 'react';
import { useAtom } from 'jotai';
import { useNavigate } from 'react-router';
import { toast } from 'sonner';
import {
  CommandDialog,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandList,
  CommandSeparator,
} from '@/components/ui/command';
import { LiveRegion } from '@/components/a11y/live-region';
import { CommandPaletteFooter } from '@/components/command-palette/command-palette-footer';
import { CommandPaletteItem } from '@/components/command-palette/command-palette-item';
import { commandPaletteOpenAtom } from '@/lib/atoms/ui';
import { getCommands } from '@/lib/commands/registry';
import { registerBuiltinCommands } from '@/lib/commands/commands';
import type {
  CommandAction,
  CommandContext,
  CommandSection,
} from '@/lib/commands/types';

const SECTION_ORDER: CommandSection[] = [
  'Navigate',
  'Create',
  'Run',
  'Settings',
  'Help',
];

interface CommandPaletteProps {
  /**
   * Telemetry hook. Fires right before a command's handler runs. Defaults to
   * `console.debug(action.id)` — the wiring point for future analytics.
   */
  onCommandExecute?: (action: CommandAction) => void;
}

function defaultTelemetry(action: CommandAction): void {
  // eslint-disable-next-line no-console
  console.debug('[command-palette]', action.id);
}

function groupBySection(actions: CommandAction[]): Map<CommandSection, CommandAction[]> {
  const grouped = new Map<CommandSection, CommandAction[]>();
  for (const section of SECTION_ORDER) {
    grouped.set(section, []);
  }
  for (const action of actions) {
    const bucket = grouped.get(action.section);
    if (bucket) bucket.push(action);
  }
  return grouped;
}

/**
 * Global command palette. Mounts once at the app root and opens via the
 * `commandPaletteOpenAtom` atom (toggled by the Quick Actions shortcut hook).
 *
 * Builds on the shadcn/ui `CommandDialog` primitive which wraps `cmdk` —
 * cmdk handles fuzzy matching, keyboard navigation, and aria-selected
 * state, so we don't reinvent that logic.
 */
export function CommandPalette({ onCommandExecute }: CommandPaletteProps = {}) {
  const [open, setOpen] = useAtom(commandPaletteOpenAtom);
  const navigate = useNavigate();
  const [query, setQuery] = useState('');
  const [version, setVersion] = useState(0);

  // Ensure built-ins are registered before the palette ever opens. Safe to
  // call repeatedly — the function guards itself.
  useEffect(() => {
    registerBuiltinCommands();
  }, []);

  // Reset the query each time the palette opens. Bump `version` so the
  // snapshot of commands reflects any late registrations.
  useEffect(() => {
    if (open) {
      setQuery('');
      setVersion((v) => v + 1);
    }
  }, [open]);

  const actions = useMemo(() => getCommands(), [open, version]);
  const grouped = useMemo(() => groupBySection(actions), [actions]);

  const telemetry = onCommandExecute ?? defaultTelemetry;

  const close = useCallback(() => setOpen(false), [setOpen]);

  const handleSelect = useCallback(
    (action: CommandAction) => {
      const ctx: CommandContext = {
        navigate: (path) => navigate(path),
        toast: (message) => toast(message),
      };
      try {
        telemetry(action);
      } catch {
        // Telemetry must never crash the handler.
      }
      close();
      // Run the handler after close so the dialog transition doesn't stall
      // the navigation / toast. Handlers that return a promise are fire-
      // and-forget at this layer.
      const maybePromise = action.handler(ctx);
      if (maybePromise && typeof maybePromise.then === 'function') {
        maybePromise.catch((err) => {
          // eslint-disable-next-line no-console
          console.error(`[command-palette] ${action.id} handler threw`, err);
        });
      }
    },
    [close, navigate, telemetry],
  );

  const liveMessage = useMemo(() => {
    if (!open) return '';
    if (actions.length === 0) return 'No commands match';
    return `${actions.length} result${actions.length === 1 ? '' : 's'}`;
  }, [actions.length, open]);

  return (
    <>
      <LiveRegion message={liveMessage} />
      <CommandDialog
        open={open}
        onOpenChange={setOpen}
        title="Command palette"
        description="Search for actions, navigation, and settings."
      >
        <CommandInput
          placeholder="Type a command or search..."
          aria-label="Command palette"
          value={query}
          onValueChange={setQuery}
        />
        <CommandList>
          <CommandEmpty>No commands match.</CommandEmpty>
          {SECTION_ORDER.map((section, index) => {
            const items = grouped.get(section) ?? [];
            if (items.length === 0) return null;
            return (
              <div key={section}>
                {index > 0 ? <CommandSeparator /> : null}
                <CommandGroup heading={section}>
                  {items.map((action) => (
                    <CommandPaletteItem
                      key={action.id}
                      action={action}
                      onSelect={handleSelect}
                    />
                  ))}
                </CommandGroup>
              </div>
            );
          })}
        </CommandList>
        <CommandPaletteFooter />
      </CommandDialog>
    </>
  );
}
