import { Card } from '@/components/ui/card';
import { Kbd } from '@/components/ui/kbd';

const SHORTCUTS = [
  { shortcut: '? / F1', action: 'Help & shortcuts' },
  { shortcut: 'Cmd/Ctrl+Shift+P', action: 'Quick actions' },
  { shortcut: 'Cmd/Ctrl+K', action: 'Session switcher' },
  { shortcut: 'Cmd/Ctrl+.', action: 'Toggle Sessions' },
  { shortcut: 'Cmd/Ctrl+Shift+F', action: 'Expand overlay' },
  { shortcut: 'Esc', action: 'Stop / dismiss' },
  { shortcut: 'N', action: 'Create task' },
  { shortcut: '/', action: 'Focus board search' },
  { shortcut: 'Enter', action: 'Open selected item' },
  { shortcut: 'S / Shift+S', action: 'Start / Stop task' },
];

export function KeyboardShortcuts() {
  return (
    <Card className="p-4">
      <h3 className="mb-3 text-sm font-medium">Keyboard shortcuts</h3>
      <div className="space-y-2">
        {SHORTCUTS.map(({ shortcut, action }) => (
          <div key={shortcut} className="flex items-center justify-between text-sm">
            <span className="text-[var(--muted-foreground)]">{action}</span>
            <Kbd>{shortcut}</Kbd>
          </div>
        ))}
      </div>
    </Card>
  );
}
