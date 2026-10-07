const dateFmt = new Intl.DateTimeFormat('en-GB', {
  day: 'numeric', month: 'short', year: 'numeric', timeZone: 'UTC',
});
const longDateFmt = new Intl.DateTimeFormat('en-GB', {
  weekday: 'short', day: 'numeric', month: 'long', year: 'numeric', timeZone: 'UTC',
});
const dateTimeFmt = new Intl.DateTimeFormat('en-GB', {
  day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit',
});
const numberFmt = new Intl.NumberFormat('en-GB');

/** "2026-09-05" -> "5 Sep 2026". Date-only values are calendar dates, so format them in UTC. */
export function formatDate(isoDate: string): string {
  return dateFmt.format(new Date(`${isoDate}T00:00:00Z`));
}

export function formatLongDate(isoDate: string): string {
  return longDateFmt.format(new Date(`${isoDate}T00:00:00Z`));
}

/** Timestamps are shown in the clinic's local time. */
export function formatDateTime(iso: string): string {
  return dateTimeFmt.format(new Date(iso));
}

export function formatCount(n: number): string {
  return numberFmt.format(n);
}

export function plural(n: number, one: string, many = `${one}s`): string {
  return `${formatCount(n)} ${n === 1 ? one : many}`;
}

/** 31 -> "31 days"; 0 -> "Due today"; -3 -> "In 3 days". */
export function describeDays(daysOverdue: number): string {
  if (daysOverdue > 0) return plural(daysOverdue, 'day');
  if (daysOverdue === 0) return 'Due today';
  return `In ${plural(-daysOverdue, 'day')}`;
}

/** Value for <input type="datetime-local"> in local time, e.g. "2026-10-06T09:14". */
export function toLocalInputValue(d: Date): string {
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}
