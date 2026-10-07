import type { FollowUpStatus } from '../api/types';
import { Icon, type IconName } from './Icon';

export const STATUS_META: Record<FollowUpStatus, { label: string; icon: IconName; hint: string }> = {
  overdue: { label: 'Overdue', icon: 'alert', hint: 'More than 14 days past the appointment' },
  missed: { label: 'Missed', icon: 'clock', hint: 'Recently missed: up to 14 days past' },
  due_soon: { label: 'Due soon', icon: 'calendar', hint: 'Appointment within the next 7 days' },
};

/** Status is text plus a distinct icon and shape; colour only reinforces it (never colour alone). */
export function StatusBadge({ status }: { status: FollowUpStatus }) {
  const meta = STATUS_META[status];
  return (
    <span className={`badge badge--${status}`}>
      <Icon name={meta.icon} size={14} />
      {meta.label}
    </span>
  );
}
