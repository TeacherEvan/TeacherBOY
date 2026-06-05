# Ms. Green Daily Journal - Implementation Plan

**Date:** 2026-06-05
**Author:** Hermes Agent (Qwen3.7-plus)
**Status:** Ready for Execution
**Source Design:** `.github/superpower/brainstorm/2026-06-05-ms-green-daily-journal-design.md`

## Overview
Implements a robust, job-oriented "Daily Journal" feature for TeacherBOY. Enhances existing image analysis with structured storage (Convex), Google Calendar cross-validation (Maton API), LINE Quick Reply UI, and automated weekly summaries (Hermes cronjob).

---

## Phase 1: Dependencies & Configuration
**Priority:** High | **Owner:** Hermes Terminal
1. **Update `requirements.txt`**:
   - Add `easyocr==1.7.1` (Lightweight local OCR fallback for messy whiteboard text).
   - Add `reportlab==4.2.0` (For generating PDF weekly summaries).
   - Run: `pip install -r requirements.txt`
2. **Verify Maton API Key**: Ensure `~/.secrets/maton.txt` is readable by the bot (already configured in memory).

---

## Phase 2: Convex Backend Schema
**Priority:** High | **Owner:** Hermes Terminal / File Edit
1. **Update `convex/schema.ts`**: Add the `debrief_sessions` table.
   ```typescript
   debriefSessions: defineTable({
     date: v.string(), // YYYY-MM-DD
     chatId: v.string(),
     timePeriod: v.optional(v.string()), // e.g., "9h12 - 10h10, Period 3"
     subject: v.optional(v.string()), // e.g., "English - foreign languages"
     lesson: v.optional(v.string()), // e.g., "Phonics"
     teacher: v.optional(v.string()), // e.g., "Teacher Evan"
     observations: v.string(), // Rich text summary
     imageUrlRef: v.optional(v.string()), // Optional: link to stored image
     validatedByCalendar: v.boolean(), // True if Maton API confirmed details
     ...timestampFields,
   })
     .index("by_date_chat", ["date", "chatId"])
     .index("by_teacher", ["teacher"]),
   ```
2. **Create Convex Mutation**: `convex/debriefSessions.ts`
   - Expose `createDebrief` mutation accepting the structured fields.
   - Expose `getWeeklyDebriefs` query (takes `chatId`, `startDate`, `endDate`) for the cron job.

---

## Phase 3: LINE Quick Reply Integration
**Priority:** Medium | **Owner:** Hermes File Edit
1. **Modify `src/handlers/message_handler.py`** (or the specific image handler routing):
   - Detect when `event.message.type == "image"`.
   - Instead of default behavior, reply with:
     ```python
     from linebot.v3.messaging import QuickReply, QuickReplyItem, MessageAction, TextMessage

     quick_reply = QuickReply(
         items=[
             QuickReplyItem(action=MessageAction(label="🔍 Analyze", text="Analyze this image")),
             QuickReplyItem(action=MessageAction(label="📝 Scrape", text="Scrape this image")),
             QuickReplyItem(action=MessageAction(label="📖 Generate Debrief", text="M")), # Fallback text trigger
         ]
     )
     msg = TextMessage(text="📸 Image received! What would you like to do?", quickReply=quick_reply)
     # reply via line_bot_api
     ```
2. Ensure the `TranslationAgent` or `ImageAnalyzerAgent` recognizes `"M"` or `"Generate Debrief"` as a direct trigger for the new debrief flow.

---

## Phase 4: Enhanced Image Analyzer & Maton Validation
**Priority:** High | **Owner:** Hermes File Edit
1. **Create `src/services/debrief_extraction_service.py`**:
   - Wrap the LLM vision call with a specific system prompt: *"Extract strictly: time_period, subject, lesson, teacher, key_observations. Return valid JSON."*
   - **Fallback OCR**: If LLM JSON parsing fails or confidence is low, run `easyocr.readtext()` on the image bytes to catch raw text, then feed *that* to the LLM for structuring.
2. **Maton API Cross-Validation**:
   - After extraction, if `teacher` or `subject` is ambiguous, call the Maton API (via `~/.secrets/maton.txt`) to check the teacher's Google Calendar for that `date` and `timePeriod`.
   - If a matching calendar event is found (e.g., "Period 3: English with Teacher Evan"), auto-fill missing fields and set `validatedByCalendar: true`.
3. **Save to Convex**: Call the new `createDebrief` mutation with the finalized structured data.

---

## Phase 5: Parent-Facing Message Formatter
**Priority:** Medium | **Owner:** Hermes File Edit
1. **Create `src/services/debrief_formatter.py`**:
   - A simple templating service that takes the `debriefSessions` record and renders it.
   - Template logic:
     ```python
     def format_parent_message(session: dict) -> str:
         date = session['date']
         period = session.get('timePeriod', 'the day')
         subject = session.get('subject', 'class')
         lesson = session.get('lesson', 'the lesson')
         teacher = session.get('teacher', 'the teacher')
         
         return (
             f"📅 *Today, {date}* ✨\n\n"
             f"As the day blessed us with the magic of knowledge, during {period}, "
             f"{teacher} spoiled the children with fun {lesson} lessons 🎵 in {subject}, "
             f"focusing on each individual student's needs.\n\n"
             f"📝 *Key Observations:* {session['observations']}\n\n"
             f"🌟 What a wonderful day of learning!"
         )
     ```
2. **Update `ImageAnalyzerAgent`**: After Convex save succeeds, generate this message and push it to the LINE chat.

---

## Phase 6: Hermes Cronjob for Weekly Summary
**Priority:** Low (Stretch) | **Owner:** Hermes Cronjob Tool
1. Use the `cronjob` tool to create a scheduled job:
   - **Schedule:** `0 16 * * 5` (Every Friday at 4:00 PM Bangkok time).
   - **Prompt:** "Query Convex `getWeeklyDebriefs` for chatId=[group_id] from last Monday to Friday. Synthesize into a single 'Weekly Journal Summary' using `debrief_formatter`. Send via LINE to the group."
   - **Toolsets:** `["terminal", "web"]` (to call Convex HTTP endpoint or use local python script).
   - *Note:* Will require a lightweight Python script in `scripts/weekly_debrief_summary.py` that authenticates with Convex and sends the LINE message.

---

## Phase 7: Testing & Verification
**Priority:** High | **Owner:** Hermes Terminal
1. Send a mock image to the bot.
2. Verify Quick Reply buttons appear.
3. Tap "📖 Generate Debrief" (or type "M").
4. Check Convex dashboard to ensure `debriefSessions` record exists with correct fields.
5. Check LINE chat for the formatted, emoji-rich parent message.
6. Verify Maton API logs show calendar validation attempt.

---

## Execution Strategy
I will execute this plan phase by phase. I will start with **Phase 1 & 2** (Dependencies and Convex Schema) and report back with tool output before proceeding to Phase 3. 

Shall I begin executing Phase 1 now?
