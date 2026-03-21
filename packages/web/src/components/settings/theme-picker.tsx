import { useAtom, useSetAtom } from 'jotai';
import { Sun, Moon, Monitor } from 'lucide-react';
import { themeModeAtom, setThemeModeAtom } from '@/lib/atoms/theme';
import { Card } from '@/components/ui/card';
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group';

type ThemeMode = 'system' | 'dark' | 'light';

const MODES: { value: ThemeMode; icon: typeof Sun; label: string }[] = [
  { value: 'system', icon: Monitor, label: 'System' },
  { value: 'dark', icon: Moon, label: 'Dark' },
  { value: 'light', icon: Sun, label: 'Light' },
];

export function ThemePicker() {
  const [mode] = useAtom(themeModeAtom);
  const setMode = useSetAtom(setThemeModeAtom);

  return (
    <Card className="p-4">
      <h3 className="mb-3 text-sm font-medium">Theme</h3>
      <ToggleGroup
        type="single"
        value={mode}
        onValueChange={(value) => {
          if (value) setMode(value as ThemeMode);
        }}
        className="flex gap-2"
      >
        {MODES.map(({ value, icon: Icon, label }) => (
          <ToggleGroupItem
            key={value}
            value={value}
            className="flex flex-1 items-center justify-center gap-2"
          >
            <Icon className="size-4" />
            {label}
          </ToggleGroupItem>
        ))}
      </ToggleGroup>
    </Card>
  );
}
