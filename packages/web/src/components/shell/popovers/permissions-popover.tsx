import { useAtom } from 'jotai';
import { composerAccessAtom, type ComposerAccess } from '@/lib/atoms/shell';
import { PopoverPanel, PopoverTitle, PopoverItem, useShellPopover } from '../popover';

interface AccessOption {
  value: ComposerAccess;
  label: string;
  desc: string;
  icon: React.ReactNode;
}

const OPTIONS: AccessOption[] = [
  {
    value: 'full',
    label: 'Full access',
    desc: 'Read, write, run commands',
    icon: <span style={{ color: 'var(--kagan-rail-review)' }}>!</span>,
  },
  {
    value: 'workspace',
    label: 'Workspace only',
    desc: 'No commands outside worktree',
    icon: <span style={{ color: 'var(--primary)' }}>W</span>,
  },
  {
    value: 'readonly',
    label: 'Read-only',
    desc: 'Inspect, no mutations',
    icon: <span style={{ color: 'var(--kagan-rail-running)' }}>R</span>,
  },
];

export function PermissionsPopover() {
  const [access, setAccess] = useAtom(composerAccessAtom);
  const { close } = useShellPopover('permissions', 'right');

  return (
    <PopoverPanel kind="permissions">
      <PopoverTitle>Permissions</PopoverTitle>
      {OPTIONS.map((opt) => (
        <PopoverItem
          key={opt.value}
          icon={opt.icon}
          label={opt.label}
          desc={opt.desc}
          active={access === opt.value}
          onClick={() => {
            setAccess(opt.value);
            close();
          }}
        />
      ))}
    </PopoverPanel>
  );
}
