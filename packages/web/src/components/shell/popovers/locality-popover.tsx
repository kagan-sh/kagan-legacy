import { useAtom } from 'jotai';
import { composerLocalityAtom, type ComposerLocality } from '@/lib/atoms/shell';
import { PopoverPanel, PopoverTitle, PopoverItem, useShellPopover } from '../popover';

interface LocalityOption {
  value: ComposerLocality;
  label: string;
  desc: string;
  icon: React.ReactNode;
}

const OPTIONS: LocalityOption[] = [
  {
    value: 'local',
    label: 'Local',
    desc: 'Agent runs on this machine',
    icon: <span style={{ color: 'var(--primary)' }}>◉</span>,
  },
  {
    value: 'remote',
    label: 'Remote',
    desc: 'Agent runs on remote server',
    icon: <span style={{ color: 'var(--kagan-rail-running)' }}>◎</span>,
  },
];

export function LocalityPopover() {
  const [locality, setLocality] = useAtom(composerLocalityAtom);
  const { close } = useShellPopover('locality', 'right');

  return (
    <PopoverPanel kind="locality">
      <PopoverTitle>Locality</PopoverTitle>
      {OPTIONS.map((opt) => (
        <PopoverItem
          key={opt.value}
          icon={opt.icon}
          label={opt.label}
          desc={opt.desc}
          active={locality === opt.value}
          onClick={() => {
            setLocality(opt.value);
            close();
          }}
        />
      ))}
    </PopoverPanel>
  );
}
