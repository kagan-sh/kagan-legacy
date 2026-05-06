import { Card } from '@/components/ui/card';
import { Kbd } from '@/components/ui/kbd';

const SHORTCUTS = [
  { keys: '? / F1', action: 'Help & Shortcuts' },
  { keys: 'Cmd/Ctrl+Shift+P', action: 'Quick Actions' },
  { keys: 'Cmd/Ctrl+K', action: 'Session Switcher' },
  { keys: 'Cmd/Ctrl+.', action: 'Toggle AI Panel' },
  { keys: 'Cmd/Ctrl+Shift+F', action: 'Fullscreen AI Panel' },
  { keys: 'Esc', action: 'Stop / dismiss' },
  { keys: 'N', action: 'Create task' },
  { keys: '/', action: 'Focus board search' },
  { keys: 'Enter', action: 'Open selected item' },
  { keys: 'S / Shift+S', action: 'Start / Stop task' },
];

export function KeyboardShortcuts() {
  return (
    <Card className="p-4">
      <h3 className="mb-3 text-sm font-medium">Keyboard Shortcuts</h3>
      <div className="space-y-2">
        {SHORTCUTS.map(({ keys, action }) => (
          <div key={keys} className="flex items-center justify-between text-sm">
            <span className="text-[var(--muted-foreground)]">{action}</span>
            <Kbd>{keys}</Kbd>
          </div>
        ))}
      </div>
    </Card>
  );
}
