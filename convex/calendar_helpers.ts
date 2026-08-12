import { clientError } from "./client_errors";

export type CalendarScope = {
  lineUserId: string;
  sourceChatId: string;
};

export type CalendarEventRecord<TId = string> = CalendarScope & {
  _id: TId;
  legacyEventId: string;
  title: string;
  eventDate: string;
  reminderDays: number[];
  notifiedDates: string[];
};

const DAY_IN_MS = 24 * 60 * 60 * 1000;
const ISO_DATE_PATTERN = /^(\d{4})-(\d{2})-(\d{2})$/;

export function hasMatchingOwnershipScope(
  event: CalendarScope,
  scope: CalendarScope,
): boolean {
  return (
    event.lineUserId === scope.lineUserId &&
    event.sourceChatId === scope.sourceChatId
  );
}

export function requireIsoDate(value: string, fieldName: string): string {
  const match = ISO_DATE_PATTERN.exec(value);
  if (!match) {
    throw clientError("invalid_iso_date", `Invalid ${fieldName}: ${value}`);
  }

  const [, year, month, day] = match;
  const yearNumber = Number(year);
  const monthNumber = Number(month);
  const dayNumber = Number(day);
  const timestamp = Date.UTC(yearNumber, monthNumber - 1, dayNumber);
  const normalized = new Date(timestamp);

  if (
    normalized.getUTCFullYear() !== yearNumber ||
    normalized.getUTCMonth() !== monthNumber - 1 ||
    normalized.getUTCDate() !== dayNumber
  ) {
    throw clientError("invalid_iso_date", `Invalid ${fieldName}: ${value}`);
  }

  return value;
}

export function diffInDays(eventDate: string, today: string): number {
  const [eventYear, eventMonth, eventDay] = requireIsoDate(eventDate, "eventDate")
    .split("-")
    .map(Number);
  const [todayYear, todayMonth, todayDay] = requireIsoDate(today, "today")
    .split("-")
    .map(Number);

  return Math.round(
    (Date.UTC(eventYear, eventMonth - 1, eventDay) -
      Date.UTC(todayYear, todayMonth - 1, todayDay)) /
      DAY_IN_MS,
  );
}

export function resolveUpsertExistingEvent<TEvent extends CalendarEventRecord>(options: {
  scopedLegacyMatches: TEvent[];
  explicitEvent: TEvent | null;
  legacyEventId: string;
  sourceChatId: string;
}): TEvent | null {
  const { scopedLegacyMatches, explicitEvent, legacyEventId, sourceChatId } = options;

  if (scopedLegacyMatches.length > 1) {
    throw clientError(
      "ambiguous_legacy_match",
      `Ambiguous legacy calendar event match for ${legacyEventId} in ${sourceChatId}`,
    );
  }

  return scopedLegacyMatches[0] ?? explicitEvent;
}

export function validateReminderNotification(
  event: CalendarEventRecord<unknown>,
  reminderDay: number,
  notifiedDate: string,
): void {
  const normalizedReminderDay = Math.max(0, Math.floor(reminderDay));
  const normalizedNotifiedDate = requireIsoDate(notifiedDate, "notifiedDate");

  if (!event.reminderDays.includes(normalizedReminderDay)) {
    throw clientError(
      "reminder_day_not_configured",
      `Reminder day ${normalizedReminderDay} is not configured for event ${event._id}`,
    );
  }

  const expectedReminderDay = diffInDays(event.eventDate, normalizedNotifiedDate);
  if (expectedReminderDay !== normalizedReminderDay) {
    throw clientError(
      "reminder_day_mismatch",
      `Reminder day ${normalizedReminderDay} does not match event ${event._id} for notified date ${normalizedNotifiedDate}`,
    );
  }
}