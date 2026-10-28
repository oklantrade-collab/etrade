/**
 * marketSchedule.ts
 * Exact US Stock Market (NYSE / NASDAQ) calendar, timekeeping (America/New_York), and bell scheduling.
 */

export interface NYCTimeInfo {
  year: number;
  month: number; // 1-12
  day: number; // 1-31
  dayOfWeek: number; // 0=Sunday, 1=Monday ... 6=Saturday
  hours: number;
  minutes: number;
  seconds: number;
  timeStr: string; // "HH:MM:SS"
  dateStr: string; // "YYYY-MM-DD"
  totalSecondsToday: number;
}

export interface MarketBellEvent {
  type: 'open' | 'close';
  targetTimeStr: string;
  targetSeconds: number;
  secondsRemaining: number;
  countdownStr: string;
  isToday: boolean;
  statusText: string;
}

/**
 * Get current date & time components in America/New_York timezone
 */
export function getNYCDateTime(referenceDate: Date = new Date()): NYCTimeInfo {
  const formatter = new Intl.DateTimeFormat('en-US', {
    timeZone: 'America/New_York',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
    weekday: 'short',
  });

  const parts = formatter.formatToParts(referenceDate);
  let year = 2026, month = 1, day = 1, hours = 0, minutes = 0, seconds = 0;
  let weekdayStr = 'Mon';

  for (const p of parts) {
    if (p.type === 'year') year = parseInt(p.value, 10);
    else if (p.type === 'month') month = parseInt(p.value, 10);
    else if (p.type === 'day') day = parseInt(p.value, 10);
    else if (p.type === 'hour') hours = parseInt(p.value, 10);
    else if (p.type === 'minute') minutes = parseInt(p.value, 10);
    else if (p.type === 'second') seconds = parseInt(p.value, 10);
    else if (p.type === 'weekday') weekdayStr = p.value;
  }

  // Map weekday to 0-6 (Sun-Sat)
  const weekdayMap: Record<string, number> = {
    'Sun': 0, 'Mon': 1, 'Tue': 2, 'Wed': 3, 'Thu': 4, 'Fri': 5, 'Sat': 6
  };
  const dayOfWeek = weekdayMap[weekdayStr] ?? 1;

  const totalSecondsToday = hours * 3600 + minutes * 60 + seconds;
  const timeStr = `${String(hours).padStart(2, '0')}:${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`;
  const dateStr = `${year}-${String(month).padStart(2, '0')}-${String(day).padStart(2, '0')}`;

  return {
    year,
    month,
    day,
    dayOfWeek,
    hours,
    minutes,
    seconds,
    timeStr,
    dateStr,
    totalSecondsToday
  };
}

/**
 * Calculate Easter Sunday for a given year (Meeus/Jones/Butcher algorithm)
 */
function getEasterSunday(year: number): { month: number, day: number } {
  const a = year % 19;
  const b = Math.floor(year / 100);
  const c = year % 100;
  const d = Math.floor(b / 4);
  const e = b % 4;
  const f = Math.floor((b + 8) / 25);
  const g = Math.floor((b - f + 1) / 3);
  const h = (19 * a + b - d - g + 15) % 30;
  const i = Math.floor(c / 4);
  const k = c % 4;
  const l = (32 + 2 * e + 2 * i - h - k) % 7;
  const m = Math.floor((a + 11 * h + 22 * l) / 451);
  const month = Math.floor((h + l - 7 * m + 114) / 31);
  const day = ((h + l - 7 * m + 114) % 31) + 1;
  return { month, day };
}

/**
 * Check if a date is Good Friday (Stock market holiday: 2 days before Easter)
 */
function isGoodFriday(year: number, month: number, day: number): boolean {
  const easter = getEasterSunday(year);
  const easterDate = new Date(Date.UTC(year, easter.month - 1, easter.day));
  const goodFridayDate = new Date(easterDate.getTime() - 2 * 24 * 60 * 60 * 1000);
  return goodFridayDate.getUTCMonth() + 1 === month && goodFridayDate.getUTCDate() === day;
}

/**
 * Check if the date is an official US stock market holiday (NYSE / NASDAQ)
 */
export function isMarketHoliday(year: number, month: number, day: number, dayOfWeek: number): { isHoliday: boolean, name?: string } {
  // Weekend
  if (dayOfWeek === 0 || dayOfWeek === 6) {
    return { isHoliday: true, name: 'Fin de semana' };
  }

  // 1. New Year's Day (Jan 1, or observed Dec 31 / Jan 2)
  if (month === 1 && day === 1) return { isHoliday: true, name: "Año Nuevo" };
  if (month === 1 && day === 2 && dayOfWeek === 1) return { isHoliday: true, name: "Año Nuevo (Observado)" };

  // 2. Martin Luther King Jr. Day (Third Monday in January)
  if (month === 1 && dayOfWeek === 1 && day >= 15 && day <= 21) {
    return { isHoliday: true, name: "Martin Luther King Jr. Day" };
  }

  // 3. Washington's Birthday / Presidents' Day (Third Monday in February)
  if (month === 2 && dayOfWeek === 1 && day >= 15 && day <= 21) {
    return { isHoliday: true, name: "Presidents' Day" };
  }

  // 4. Good Friday
  if (isGoodFriday(year, month, day)) {
    return { isHoliday: true, name: "Viernes Santo (Good Friday)" };
  }

  // 5. Memorial Day (Last Monday in May)
  if (month === 5 && dayOfWeek === 1 && day >= 25) {
    return { isHoliday: true, name: "Memorial Day" };
  }

  // 6. Juneteenth (June 19, or observed Fri/Mon)
  if (month === 6) {
    if (day === 19 && dayOfWeek >= 1 && dayOfWeek <= 5) return { isHoliday: true, name: "Juneteenth" };
    if (day === 18 && dayOfWeek === 5) return { isHoliday: true, name: "Juneteenth (Observado)" };
    if (day === 20 && dayOfWeek === 1) return { isHoliday: true, name: "Juneteenth (Observado)" };
  }

  // 7. Independence Day (July 4, or observed Fri/Mon)
  if (month === 7) {
    if (day === 4 && dayOfWeek >= 1 && dayOfWeek <= 5) return { isHoliday: true, name: "Día de la Independencia" };
    if (day === 3 && dayOfWeek === 5) return { isHoliday: true, name: "Día de la Independencia (Observado)" };
    if (day === 5 && dayOfWeek === 1) return { isHoliday: true, name: "Día de la Independencia (Observado)" };
  }

  // 8. Labor Day (First Monday in September)
  if (month === 9 && dayOfWeek === 1 && day <= 7) {
    return { isHoliday: true, name: "Labor Day" };
  }

  // 9. Thanksgiving Day (Fourth Thursday in November)
  if (month === 11 && dayOfWeek === 4 && day >= 22 && day <= 28) {
    return { isHoliday: true, name: "Acción de Gracias (Thanksgiving)" };
  }

  // 10. Christmas Day (Dec 25, or observed Dec 24/26)
  if (month === 12) {
    if (day === 25 && dayOfWeek >= 1 && dayOfWeek <= 5) return { isHoliday: true, name: "Navidad" };
    if (day === 24 && dayOfWeek === 5) return { isHoliday: true, name: "Navidad (Observada)" };
    if (day === 26 && dayOfWeek === 1) return { isHoliday: true, name: "Navidad (Observada)" };
  }

  return { isHoliday: false };
}

/**
 * Check if the date is an early close day (market closes at 1:00 PM ET / 13:00)
 */
export function isEarlyCloseDay(year: number, month: number, day: number, dayOfWeek: number): boolean {
  // Day before Independence Day (July 3 if weekday)
  if (month === 7 && day === 3 && dayOfWeek >= 1 && dayOfWeek <= 4) return true;
  // Black Friday (Day after Thanksgiving, 4th Friday of November)
  if (month === 11 && dayOfWeek === 5 && day >= 23 && day <= 29) return true;
  // Christmas Eve (Dec 24 if weekday)
  if (month === 12 && day === 24 && dayOfWeek >= 1 && dayOfWeek <= 4) return true;
  return false;
}

/**
 * Format remaining seconds into "HHh MMm SSs" or "MMm SSs"
 */
export function formatCountdown(totalSeconds: number): string {
  if (totalSeconds <= 0) return '00s';
  const h = Math.floor(totalSeconds / 3600);
  const m = Math.floor((totalSeconds % 3600) / 60);
  const s = totalSeconds % 60;

  if (h > 0) {
    return `${h}h ${String(m).padStart(2, '0')}m ${String(s).padStart(2, '0')}s`;
  }
  return `${String(m).padStart(2, '0')}m ${String(s).padStart(2, '0')}s`;
}

/**
 * Returns upcoming bell schedule and details based on current NYC time
 */
export function getNextMarketBellInfo(nowNYC: NYCTimeInfo = getNYCDateTime()): MarketBellEvent {
  const { year, month, day, dayOfWeek, totalSecondsToday } = nowNYC;
  const holiday = isMarketHoliday(year, month, day, dayOfWeek);
  const isEarlyClose = isEarlyCloseDay(year, month, day, dayOfWeek);

  const openSeconds = 9 * 3600 + 30 * 60; // 09:30:00 (34200)
  const closeSeconds = isEarlyClose ? (13 * 3600) : (16 * 3600); // 16:00:00 (57600) or 13:00:00 (46800)
  const closeTimeStr = isEarlyClose ? '13:00:00' : '16:00:00';

  // Case 1: Today is a weekend or holiday
  if (holiday.isHoliday) {
    return {
      type: 'open',
      targetTimeStr: '09:30:00',
      targetSeconds: openSeconds,
      secondsRemaining: 0,
      countdownStr: holiday.name || 'Mercado Cerrado',
      isToday: false,
      statusText: `CERRADO (${holiday.name})`
    };
  }

  // Case 2: Today is a trading day, before 09:30 AM ET
  if (totalSecondsToday < openSeconds) {
    const diff = openSeconds - totalSecondsToday;
    return {
      type: 'open',
      targetTimeStr: '09:30:00',
      targetSeconds: openSeconds,
      secondsRemaining: diff,
      countdownStr: formatCountdown(diff),
      isToday: true,
      statusText: 'PRE-MERCADO (Esperando Apertura 09:30 ET)'
    };
  }

  // Case 3: Today is a trading day, during regular market hours (09:30 - 16:00)
  if (totalSecondsToday >= openSeconds && totalSecondsToday < closeSeconds) {
    const diff = closeSeconds - totalSecondsToday;
    return {
      type: 'close',
      targetTimeStr: closeTimeStr,
      targetSeconds: closeSeconds,
      secondsRemaining: diff,
      countdownStr: formatCountdown(diff),
      isToday: true,
      statusText: 'MERCADO ABIERTO (En curso)'
    };
  }

  // Case 4: Today is a trading day, after market close (> 16:00)
  return {
    type: 'open',
    targetTimeStr: '09:30:00',
    targetSeconds: openSeconds,
    secondsRemaining: 0,
    countdownStr: 'Sesión Finalizada',
    isToday: false,
    statusText: 'POST-CIERRE (Mercado Cerrado)'
  };
}
