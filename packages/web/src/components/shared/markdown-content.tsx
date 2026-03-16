import { useMemo } from 'react';
import DOMPurify from 'dompurify';
import { marked } from 'marked';
import { cn } from '@/lib/utils';

interface MarkdownContentProps {
  content: string;
  className?: string;
}

const BASE_MARKDOWN_CLASSNAME =
  'prose prose-sm max-w-none text-[0.9375rem] leading-6 [&>*:first-child]:mt-0 [&>*:last-child]:mb-0 prose-headings:mb-1.5 prose-headings:mt-3 prose-headings:font-semibold prose-headings:tracking-tight prose-h1:text-lg prose-h2:text-base prose-h3:text-[0.95rem] prose-p:my-1.5 prose-p:leading-6 prose-ul:my-1.5 prose-ul:list-disc prose-ul:pl-6 prose-ol:my-1.5 prose-ol:list-decimal prose-ol:pl-6 prose-li:my-0.5 prose-li:marker:text-[var(--muted-foreground)] prose-hr:my-3 prose-blockquote:my-2 prose-blockquote:border-l-2 prose-blockquote:pl-3 prose-blockquote:italic prose-a:underline prose-a:underline-offset-2 prose-code:bg-[var(--surface-2)] prose-code:px-1 prose-code:py-0.5 prose-code:font-code prose-code:text-[0.8em] prose-code:before:content-none prose-code:after:content-none prose-pre:my-2 prose-pre:overflow-x-auto prose-pre:border prose-pre:border-[color:var(--border-subtle)] prose-pre:bg-[var(--surface-1)] prose-pre:p-3 prose-pre:font-code prose-pre:text-[11px] prose-pre:leading-[1.45]';

export function MarkdownContent({ content, className }: MarkdownContentProps) {
  const html = useMemo(() => {
    const raw = marked.parse(content, { async: false }) as string;
    return DOMPurify.sanitize(raw);
  }, [content]);

  return (
    <div
      className={cn(BASE_MARKDOWN_CLASSNAME, className)}
      dangerouslySetInnerHTML={{ __html: html }}
    />
  );
}
