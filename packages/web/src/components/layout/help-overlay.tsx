import { useState } from 'react';
import { useAtom } from 'jotai';
import { ExternalLink, GitBranch, HelpCircle } from 'lucide-react';
import { helpOverlayOpenAtom } from '@/lib/atoms/ui';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Kbd, KbdGroup } from '@/components/ui/kbd';
import { KAGAN_URLS, KAGAN_META } from '@/lib/constants';

type ShortcutRow = { keys: string[]; description: string };
type ShortcutSection = { title: string; rows: ShortcutRow[] };

const SHORTCUTS: ShortcutSection[] = [
  {
    title: 'Global',
    rows: [
      { keys: ['Cmd/Ctrl', 'Shift', 'P'], description: 'Open Quick Actions' },
      { keys: ['Cmd/Ctrl', 'K'], description: 'Open Session Switcher' },
      { keys: ['?', 'F1'], description: 'Help & Shortcuts' },
      { keys: ['Cmd/Ctrl', '.'], description: 'Toggle AI Panel' },
      { keys: ['Cmd/Ctrl', 'Shift', 'F'], description: 'Fullscreen AI Panel' },
      { keys: ['Esc'], description: 'Stop agent + edit last message' },
    ],
  },
  {
    title: 'Board',
    rows: [
      { keys: ['Arrow keys'], description: 'Navigate tasks and columns' },
      { keys: ['Enter'], description: 'Open selected task' },
      { keys: ['E'], description: 'Edit selected task' },
      { keys: ['Shift', '←', '→'], description: 'Move task between lanes' },
    ],
  },
  {
    title: 'Task & Session',
    rows: [
      { keys: ['Open Chat'], description: 'Watch the current task workspace in the chat rail' },
      { keys: ['Worker', 'Reviewer'], description: 'Switch the current task workspace lane view' },
      { keys: ['Cmd/Ctrl', 'K'], description: 'Switch between sessions' },
    ],
  },
];

const FLOWS = [
  {
    title: 'Quick Start',
    body: 'Create or open a project from Welcome, then go to Board to start orchestration.',
  },
  {
    title: 'Managed Run Flow',
    body: 'Create a task and start a managed run in the background, then watch the task workspace for diff, evidence, and verdicts.',
  },
  {
    title: 'Interactive Attach Flow',
    body: 'Create a task and attach an interactive run when you want to work live in the same task workspace.',
  },
  {
    title: 'Orchestrator Control Flow',
    body: 'Use Session Switcher (Cmd/Ctrl+K) to open orchestrator sessions for planning, prioritization, and multi-task coordination.',
  },
];

const CONCEPTS = [
  {
    title: 'Project and Repositories',
    body: 'A project scopes board state, tasks, and repository context for all agent interactions.',
  },
  {
    title: 'Task vs Orchestrator Sessions',
    body: 'Task sessions are execution-lane streams, while orchestrator sessions are high-level planning chats.',
  },
  {
    title: 'Runs',
    body: 'Managed runs optimize throughput; watch keeps you on the task workspace; attach optimizes control. Choose based on uncertainty and risk.',
  },
  {
    title: 'Review Discipline',
    body: 'Use task detail and diff panels to validate outcomes before approving and merging.',
  },
];

export function HelpOverlay() {
  const [open, setOpen] = useAtom(helpOverlayOpenAtom);
  const [query, setQuery] = useState('');

  const normalizedQuery = query.trim().toLowerCase();

  const filteredShortcutSections = normalizedQuery
    ? SHORTCUTS
        .map((section) => ({
          ...section,
          rows: section.rows.filter((row) => {
            const keyText = row.keys.join(' ').toLowerCase();
            return (
              section.title.toLowerCase().includes(normalizedQuery) ||
              keyText.includes(normalizedQuery) ||
              row.description.toLowerCase().includes(normalizedQuery)
            );
          }),
        }))
        .filter((section) => section.rows.length > 0)
    : SHORTCUTS;

  const filteredFlows = normalizedQuery
    ? FLOWS.filter(
        (item) =>
          item.title.toLowerCase().includes(normalizedQuery) ||
          item.body.toLowerCase().includes(normalizedQuery),
      )
    : FLOWS;

  const filteredConcepts = normalizedQuery
    ? CONCEPTS.filter(
        (item) =>
          item.title.toLowerCase().includes(normalizedQuery) ||
          item.body.toLowerCase().includes(normalizedQuery),
      )
    : CONCEPTS;

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogContent className="max-w-3xl gap-3 p-0">
        <DialogHeader className="border-b border-[color:var(--border-subtle)] px-5 pt-5 pb-4">
          <DialogTitle className="flex items-center gap-2 text-base">
            <HelpCircle className="size-4" />
            Kagan Help
          </DialogTitle>
          <DialogDescription>Search shortcuts, workflows, and concepts.</DialogDescription>
          <Input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Search commands or flows..."
            className="mt-2"
          />
        </DialogHeader>

        <Tabs defaultValue="shortcuts" className="min-h-0 px-5 pb-5">
          <TabsList>
            <TabsTrigger value="shortcuts">Shortcuts</TabsTrigger>
            <TabsTrigger value="flows">Flows</TabsTrigger>
            <TabsTrigger value="concepts">Concepts</TabsTrigger>
            <TabsTrigger value="about">About</TabsTrigger>
          </TabsList>

          <TabsContent value="shortcuts" className="mt-3">
            <ScrollArea className="h-[min(65vh,34rem)] pr-3">
              <div className="space-y-5 pb-2">
                {filteredShortcutSections.length === 0 ? (
                  <p className="text-sm text-[var(--muted-foreground)]">No shortcuts match your search.</p>
                ) : (
                  filteredShortcutSections.map((section) => (
                    <section key={section.title} className="space-y-2">
                      <h3 className="text-xs font-semibold uppercase tracking-[0.14em] text-[var(--muted-foreground)]">
                        {section.title}
                      </h3>
                      <div className="space-y-1.5">
                        {section.rows.map((row) => (
                          <div
                            key={`${section.title}-${row.keys.join('-')}-${row.description}`}
                            className="flex items-center justify-between gap-3 border border-[color:var(--border-subtle)] bg-[color:var(--surface-1)] px-3 py-2"
                          >
                            <p className="text-sm text-[var(--foreground)]">{row.description}</p>
                            <KbdGroup className="gap-1">
                              {row.keys.map((key) => (
                                <Kbd key={`${section.title}-${row.description}-${key}`}>{key}</Kbd>
                              ))}
                            </KbdGroup>
                          </div>
                        ))}
                      </div>
                    </section>
                  ))
                )}
              </div>
            </ScrollArea>
          </TabsContent>

          <TabsContent value="flows" className="mt-3">
            <ScrollArea className="h-[min(65vh,34rem)] pr-3">
              <div className="space-y-3 pb-2">
                {filteredFlows.length === 0 ? (
                  <p className="text-sm text-[var(--muted-foreground)]">No flows match your search.</p>
                ) : (
                  filteredFlows.map((flow) => (
                    <section
                      key={flow.title}
                      className="space-y-1 border border-[color:var(--border-subtle)] bg-[color:var(--surface-1)] px-3 py-3"
                    >
                      <h3 className="text-sm font-semibold text-[var(--foreground)]">{flow.title}</h3>
                      <p className="text-sm text-[var(--muted-foreground)]">{flow.body}</p>
                    </section>
                  ))
                )}
              </div>
            </ScrollArea>
          </TabsContent>

          <TabsContent value="concepts" className="mt-3">
            <ScrollArea className="h-[min(65vh,34rem)] pr-3">
              <div className="space-y-3 pb-2">
                {filteredConcepts.length === 0 ? (
                  <p className="text-sm text-[var(--muted-foreground)]">No concepts match your search.</p>
                ) : (
                  filteredConcepts.map((concept) => (
                    <section
                      key={concept.title}
                      className="space-y-1 border border-[color:var(--border-subtle)] bg-[color:var(--surface-1)] px-3 py-3"
                    >
                      <h3 className="text-sm font-semibold text-[var(--foreground)]">{concept.title}</h3>
                      <p className="text-sm text-[var(--muted-foreground)]">{concept.body}</p>
                    </section>
                  ))
                )}
              </div>
            </ScrollArea>
          </TabsContent>

          <TabsContent value="about" className="mt-3">
            <ScrollArea className="h-[min(65vh,34rem)] pr-3">
              <div className="flex flex-col items-center gap-6 pb-2 pt-4 text-center">
                {/* Logo */}
                <div className="inline-flex items-center gap-2 bg-[color:var(--surface-1)] px-4 py-2 shadow-[var(--ambient-shadow)]">
                  <span className="font-code text-lg tracking-[0.08em]">ᘚᘛ</span>
                  <span className="font-code text-sm font-semibold uppercase tracking-[0.22em]">{KAGAN_META.name}</span>
                </div>

                {/* Tagline */}
                <p className="text-sm text-[var(--muted-foreground)]">{KAGAN_META.tagline}</p>

                {/* Attribution */}
                <div className="flex flex-col items-center gap-2 text-xs text-[var(--muted-foreground)]">
                  <span>
                    © {KAGAN_META.copyrightYear}{' '}
                    <a
                      href={KAGAN_URLS.makerx}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="underline hover:text-[var(--foreground)]"
                    >
                      {KAGAN_META.makerxName}
                    </a>
                  </span>

                  <div className="flex items-center gap-3">
                    <a
                      href={KAGAN_URLS.github}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-flex items-center gap-1 hover:text-[var(--foreground)]"
                    >
                      <GitBranch className="size-3" />
                      GitHub
                      <ExternalLink className="size-3" />
                    </a>
                    <span className="text-[var(--border-subtle)]">·</span>
                    <a
                      href={KAGAN_URLS.license}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="hover:text-[var(--foreground)]"
                    >
                      {KAGAN_META.license} License
                    </a>
                  </div>
                </div>

                {/* Links */}
                <div className="flex flex-wrap justify-center gap-3 text-xs">
                  <a
                    href={KAGAN_URLS.docs}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center gap-1 text-[var(--muted-foreground)] hover:text-[var(--foreground)]"
                  >
                    Documentation
                    <ExternalLink className="size-3" />
                  </a>
                  <a
                    href={KAGAN_URLS.discord}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center gap-1 text-[var(--muted-foreground)] hover:text-[var(--foreground)]"
                  >
                    Discord
                    <ExternalLink className="size-3" />
                  </a>
                  <a
                    href={KAGAN_URLS.pypi}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center gap-1 text-[var(--muted-foreground)] hover:text-[var(--foreground)]"
                  >
                    PyPI
                    <ExternalLink className="size-3" />
                  </a>
                </div>
              </div>
            </ScrollArea>
          </TabsContent>
        </Tabs>
      </DialogContent>
    </Dialog>
  );
}
