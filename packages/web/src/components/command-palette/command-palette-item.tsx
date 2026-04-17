import { CommandItem } from '@/components/ui/command';
import { Kbd } from '@/components/ui/kbd';
import type { CommandAction } from '@/lib/commands/types';

interface CommandPaletteItemProps {
  action: CommandAction;
  onSelect: (action: CommandAction) => void;
}

/**
 * Single row in the command palette list. Icon → title → optional shortcut.
 *
 * `value` is fed to cmdk's fuzzy matcher and combines title, id, and
 * keywords so users can match on any of them ("new" finds "Create task").
 */
export function CommandPaletteItem({ action, onSelect }: CommandPaletteItemProps) {
  const Icon = action.icon;
  const searchValue = [action.title, action.id, ...(action.keywords ?? [])].join(' ');

  return (
    <CommandItem
      value={searchValue}
      data-command-id={action.id}
      onSelect={() => onSelect(action)}
    >
      {Icon ? <Icon className="size-4" aria-hidden="true" /> : null}
      <span className="flex-1 truncate">{action.title}</span>
      {action.shortcut && action.shortcut.length > 0 ? (
        <span className="ml-auto flex items-center gap-1">
          {action.shortcut.map((key, index) => (
            <Kbd key={`${action.id}-shortcut-${index}`}>{key}</Kbd>
          ))}
        </span>
      ) : null}
    </CommandItem>
  );
}
