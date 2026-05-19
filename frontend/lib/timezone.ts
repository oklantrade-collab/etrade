'use client'

/**
 * Gets the current system timezone from localStorage, or defaults to America/Lima.
 */
export function getAppTimezone(): string {
  if (typeof window !== 'undefined') {
    return localStorage.getItem('app_timezone') || 'America/Lima';
  }
  return 'America/Lima';
}

/**
 * Formats a Date object or an ISO timestamp string to a selected timezone.
 * Defaults to 'America/Lima' if no global setting is active.
 * 
 * @param dateStr The date string or object to format
 * @param formatType 'date' (e.g. 19/05/2026), 'time' (e.g. 14:32:05), or 'both'
 */
export function formatDateInTimezone(
  dateStr: string | Date | null | undefined,
  formatType: 'date' | 'time' | 'both' = 'both'
): string {
  if (!dateStr) return '—';
  
  try {
    const date = typeof dateStr === 'string' ? new Date(dateStr) : dateStr;
    if (isNaN(date.getTime())) return '—';

    const tz = getAppTimezone();

    if (formatType === 'date') {
      return date.toLocaleDateString('es-PE', {
        timeZone: tz,
        day: '2-digit',
        month: '2-digit',
        year: 'numeric'
      });
    } else if (formatType === 'time') {
      return date.toLocaleTimeString('es-PE', {
        timeZone: tz,
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
        hour12: false
      });
    } else {
      return date.toLocaleString('es-PE', {
        timeZone: tz,
        day: '2-digit',
        month: '2-digit',
        year: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
        hour12: false
      });
    }
  } catch (err) {
    console.error("Error formatting date in timezone:", err);
    return '—';
  }
}
