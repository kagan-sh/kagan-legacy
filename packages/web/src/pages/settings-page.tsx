import { useCallback, useRef, useState, type ComponentType, type SVGProps } from 'react';
import { useSetAtom } from 'jotai';
import { ArrowLeft, Bot, Cog, Settings, Workflow } from 'lucide-react';
import { useNavigate } from 'react-router';
import { logoutAtom } from '@/lib/atoms/auth';
import { LiveRegion } from '@/components/a11y/live-region';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { ConnectionCard } from '@/components/settings/connection-card';
import { PreflightChecks } from '@/components/settings/preflight-checks';
import { SettingsCategoryCard } from '@/components/settings/settings-category-card';
import { SettingsSectionAdvanced } from '@/components/settings/settings-section-advanced';
import { SettingsSectionAgents } from '@/components/settings/settings-section-agents';
import { SettingsSectionWorkflow } from '@/components/settings/settings-section-workflow';
import { useSettingsForm } from '@/components/settings/use-settings-form';

type CategoryId = 'workflow' | 'agents' | 'advanced';

interface CategoryMeta {
  id: CategoryId;
  icon: ComponentType<SVGProps<SVGSVGElement>>;
  title: string;
  subtitle: string;
  description: string;
}

const CATEGORIES: CategoryMeta[] = [
  {
    id: 'workflow',
    icon: Workflow,
    title: 'Workflow',
    subtitle: 'Review, planning, and merge behavior for your tasks.',
    description: 'Controls how Kagan reviews, plans, and merges work produced by agents.',
  },
  {
    id: 'agents',
    icon: Bot,
    title: 'Agents',
    subtitle: 'Default backend, model hints, and instructions for every run.',
    description: 'Pick which agent runs by default and refine what Kagan tells it each time.',
  },
  {
    id: 'advanced',
    icon: Cog,
    title: 'Advanced',
    subtitle: 'Appearance, git identity, workspace bootstrap, and attach tooling.',
    description: 'Lower-frequency settings most users rarely need to change.',
  },
];

export function Component() {
  const logout = useSetAtom(logoutAtom);
  const navigate = useNavigate();
  const controller = useSettingsForm();
  const [activeCategory, setActiveCategory] = useState<CategoryId | null>(null);
  const sectionHeadingRef = useRef<HTMLHeadingElement | null>(null);

  const openCategory = useCallback((id: CategoryId) => {
    setActiveCategory(id);
    // Move focus to the section heading for screen readers and keyboard users.
    requestAnimationFrame(() => {
      sectionHeadingRef.current?.focus();
    });
  }, []);

  const closeCategory = useCallback(() => {
    const returningTo = activeCategory;
    setActiveCategory(null);
    // Restore focus to the originating card so keyboard flow resumes cleanly.
    requestAnimationFrame(() => {
      if (!returningTo) return;
      const trigger = document.getElementById(`settings-card-${returningTo}`);
      trigger?.focus();
    });
  }, [activeCategory]);

  const handleLogout = () => {
    logout();
    navigate('/welcome');
  };

  const activeMeta = activeCategory
    ? CATEGORIES.find((category) => category.id === activeCategory)
    : null;

  return (
    <div className="mx-auto flex w-full max-w-2xl flex-col px-4 py-10 sm:px-6">
      {/* Hero */}
      <div className="space-y-2 text-center">
        <div className="mx-auto mb-3 flex size-12 items-center justify-center text-[var(--muted-foreground)]">
          <Settings className="size-7" />
        </div>
        <h1 className="text-xl font-semibold tracking-tight">Settings</h1>
        <p className="text-sm text-[var(--muted-foreground)]">
          Configure how Kagan works with your codebase.
        </p>
      </div>

      <LiveRegion message={activeMeta ? `${activeMeta.title} settings expanded` : null} />

      {/* Category cards / expanded section */}
      <div className="mt-8">
        {activeMeta ? (
          <SettingsSectionView
            meta={activeMeta}
            headingRef={sectionHeadingRef}
            onBack={closeCategory}
          >
            {controller.loading ? (
              <div className="space-y-3" aria-busy="true">
                <div className="h-14 animate-pulse bg-[var(--muted)]" />
                <div className="h-14 animate-pulse bg-[var(--muted)]" />
                <div className="h-14 animate-pulse bg-[var(--muted)]" />
              </div>
            ) : (
              <>
                {activeMeta.id === 'workflow' && (
                  <SettingsSectionWorkflow controller={controller} />
                )}
                {activeMeta.id === 'agents' && <SettingsSectionAgents controller={controller} />}
                {activeMeta.id === 'advanced' && (
                  <SettingsSectionAdvanced controller={controller} />
                )}
              </>
            )}
          </SettingsSectionView>
        ) : (
          <CategoryList
            categories={CATEGORIES}
            activeCategory={activeCategory}
            onOpen={openCategory}
          />
        )}
      </div>

      {/* System cards — always visible under the category disclosure */}
      {!activeCategory && (
        <div className="mt-6 space-y-4">
          <ConnectionCard />
          <PreflightChecks />
        </div>
      )}

      {/* Return */}
      <div className="mt-10 flex justify-center">
        <Button
          variant="ghost"
          size="sm"
          className="text-[var(--muted-foreground)]"
          onClick={handleLogout}
        >
          <ArrowLeft className="size-3.5" />
          Return to welcome
        </Button>
      </div>
    </div>
  );
}

interface CategoryListProps {
  categories: CategoryMeta[];
  activeCategory: CategoryId | null;
  onOpen: (id: CategoryId) => void;
}

function CategoryList({ categories, activeCategory, onOpen }: CategoryListProps) {
  return (
    <div role="list" className="space-y-2">
      {categories.map((category) => (
        <div role="listitem" key={category.id}>
          <SettingsCategoryCard
            id={category.id}
            icon={category.icon}
            title={category.title}
            subtitle={category.subtitle}
            expanded={activeCategory === category.id}
            onClick={() => onOpen(category.id)}
          />
        </div>
      ))}
    </div>
  );
}

interface SectionViewProps {
  meta: CategoryMeta;
  headingRef: React.RefObject<HTMLHeadingElement | null>;
  onBack: () => void;
  children: React.ReactNode;
}

function SettingsSectionView({ meta, headingRef, onBack, children }: SectionViewProps) {
  return (
    <div
      id={`settings-panel-${meta.id}`}
      role="region"
      aria-labelledby={`settings-heading-${meta.id}`}
    >
      <Button
        variant="ghost"
        size="sm"
        onClick={onBack}
        className="-ml-2 text-[var(--muted-foreground)]"
      >
        <ArrowLeft className="size-3.5" />
        All settings
      </Button>
      <div className="mt-3 space-y-1">
        <h2
          id={`settings-heading-${meta.id}`}
          ref={headingRef}
          tabIndex={-1}
          className="text-lg font-semibold tracking-tight focus:outline-none"
        >
          {meta.title}
        </h2>
        <p className="text-sm text-[var(--muted-foreground)]">{meta.description}</p>
      </div>
      <Card className="mt-5 overflow-hidden px-5 py-5">{children}</Card>
    </div>
  );
}
