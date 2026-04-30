/**
 * MentionLink — renders `kagan#<id>` and `#<n>` tokens as clickable spans/links.
 *
 * - `kagan#<8hex>` → in-app navigation via useNavigate() to /task/<id>
 * - `#<digits>`    → external link to github.com/<slug>/issues/<n>
 *
 * Usage:
 *   <MentionLink text={rawText} githubSlug="owner/repo" />
 */
import { useNavigate } from 'react-router';

const MENTION_PATTERN = /(kagan#[0-9a-f]{8,}|#\d+)/g;

interface MentionLinkProps {
  text: string;
  /** GitHub repo slug (owner/repo) — required for resolving #N links. */
  githubSlug?: string | null;
  className?: string;
}

export function MentionLink({ text, githubSlug, className }: MentionLinkProps) {
  const navigate = useNavigate();

  const parts = text.split(MENTION_PATTERN);

  return (
    <span className={className}>
      {parts.map((part, i) => {
        if (part.startsWith('kagan#')) {
          const id = part.slice('kagan#'.length);
          return (
            <button
              key={i}
              type="button"
              className="font-mono text-[var(--primary)] underline underline-offset-2 hover:opacity-80"
              onClick={() => void navigate(`/task/${id}`)}
              title={`Open task ${part}`}
            >
              {part}
            </button>
          );
        }

        if (part.startsWith('#') && /^#\d+$/.test(part)) {
          const n = part.slice(1);
          const href = githubSlug
            ? `https://github.com/${githubSlug}/issues/${n}`
            : '#';
          return (
            <a
              key={i}
              href={href}
              target="_blank"
              rel="noopener noreferrer"
              className="font-mono text-[var(--primary)] underline underline-offset-2 hover:opacity-80"
              title={githubSlug ? `GitHub issue ${part}` : part}
            >
              {part}
            </a>
          );
        }

        return <span key={i}>{part}</span>;
      })}
    </span>
  );
}
