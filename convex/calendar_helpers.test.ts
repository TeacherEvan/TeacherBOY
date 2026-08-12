import test from "node:test";
import assert from "node:assert/strict";
import { ConvexError } from "convex/values";

import { requireReminderQueryScope } from "./calendar";
import {
  resolveUpsertExistingEvent,
  validateReminderNotification,
  type CalendarEventRecord,
} from "./calendar_helpers";

function makeEvent(overrides: Partial<CalendarEventRecord> = {}): CalendarEventRecord {
  return {
    _id: "event_1",
    legacyEventId: "legacy-1",
    lineUserId: "user_1",
    sourceChatId: "chat_1",
    title: "Team standup",
    eventDate: "2026-06-15",
    reminderDays: [7, 1, 0],
    notifiedDates: [],
    ...overrides,
  };
}

test("matching scoped legacy identity resolves to the existing event for update", () => {
  const existing = makeEvent();

  const resolved = resolveUpsertExistingEvent({
    scopedLegacyMatches: [existing],
    explicitEvent: null,
    legacyEventId: existing.legacyEventId,
    sourceChatId: existing.sourceChatId,
  });

  assert.equal(resolved?._id, existing._id);
});

test("different legacy identity in the same scope does not force an update", () => {
  const resolved = resolveUpsertExistingEvent({
    scopedLegacyMatches: [],
    explicitEvent: null,
    legacyEventId: "legacy-2",
    sourceChatId: "chat_1",
  });

  assert.equal(resolved, null);
});

test("reminder-day mismatch raises a structured client error", () => {
  const event = makeEvent({
    eventDate: "2026-06-15",
    reminderDays: [7, 1, 0],
  });

  assert.throws(
    () => validateReminderNotification(event, 7, "2026-06-14"),
    (error: unknown) => {
      assert.ok(error instanceof ConvexError);
      assert.deepEqual(error.data, {
        kind: "client_error",
        status: 400,
        code: "reminder_day_mismatch",
        message:
          "Reminder day 7 does not match event event_1 for notified date 2026-06-14",
      });
      return true;
    },
  );
});

test("getDueReminders allows a global scope when no user or chat filter is provided", () => {
  assert.deepEqual(
    requireReminderQueryScope({
      lineUserId: undefined,
      sourceChatId: undefined,
    }),
    { scope: "global" },
  );
});

test("getDueReminders rejects mixed user and chat scope", () => {
  assert.throws(
    () =>
      requireReminderQueryScope({
        lineUserId: "user_1",
        sourceChatId: "chat_1",
      }),
    (error: unknown) => {
      assert.ok(error instanceof ConvexError);
      assert.deepEqual(error.data, {
        kind: "client_error",
        status: 400,
        code: "mixed_query_scope",
        message: "getDueReminders accepts either lineUserId or sourceChatId, not both",
      });
      return true;
    },
  );
});