import { Badge } from '@/components/ui/badge';
import { cn } from '@/lib/utils';
import type { TaskStatus } from '@kagan/shared-api-client';
import { STATUS_LABELS, STATUS_COLORS } from '@/lib/utils/constants';

interface StatusBadgeProps {
  status: TaskStatus;
  className?: string;
}

export function StatusBadge({ status, className }: StatusBadgeProps) {
  return (
    <Badge variant="outline" role="status" className={cn('gap-1.5', className)}>
      <span
        className="size-2 rounded-full"
        style={{ backgroundColor: STATUS_COLORS[status] }}
        aria-hidden="true"
      />
      {STATUS_LABELS[status] ?? status}
    </Badge>
  );
}
