# Ms. Green Daily Journal Feature Design

**Date:** 2026-06-05
**Status:** Approved for Implementation Planning

## Overview
A new workflow for the TeacherBOY (Ms. Green) bot that allows users to automatically analyze journal images, store the extracted data in a persistent backend, and generate a warm, emoji-rich debrief message suitable for parents.

## 1. Trigger & UI Flow
- The user sends an image to the chat.
- The bot detects the image and replies with a message containing LINE Quick Reply buttons: **[ Analyze ] [ Scrape ] [ Generate Debrief ]**.
- The user taps **[ Generate Debrief ]** (with a fallback text trigger like "M" or "Ms Green debrief" still supported for manual invocation).

## 2. Data Extraction & Storage
- The `ImageAnalyzerAgent` processes the image using a specialized "Journal Debrief" system prompt. This prompt instructs the LLM to extract structured fields: `time_period`, `subject`, `lesson`, `teacher`, and `key_observations`.
- The bot saves this structured JSON to a new Convex backend mutation (e.g., `debriefSessions.create`), indexed by `date` and `chat_id` to build a persistent, searchable journal.

## 3. Parent-Facing Message Generation
- Once the structured data is safely stored in Convex, the bot passes this data to a formatting service (e.g., an extension of `DebriefPromptBuilder`).
- This service uses a predefined, warm, and engaging template to generate the parent-facing message, injecting suitable emojis for visual appeal.
- **Example Output:** "📅 *Today, [Date]* ✨ As the day blessed us with the magic of knowledge, in the 3rd period, Teacher Evan spoiled the children with fun Phonics lessons 🎵, focusing on each individual student's needs. On Period 4, the students had great fun in Science 🧪, led by the amazing Teacher Ana, who showed them exciting experiments! 🌟"
- The bot sends this rich, formatted message back to the chat, completing the flow.

## Next Steps
- Transition to `superpower-plan` to create a step-by-step implementation plan, including Convex schema updates, new prompt templates, and LINE Quick Reply integration.
