import {
  httpActionGeneric,
  httpRouter,
  makeFunctionReference,
} from "convex/server";

import {
  clientError,
  getErrorMessage,
  isStructuredClientError,
} from "./client_errors";

const http = httpRouter();

function jsonResponse(status: number, payload: unknown): Response {
  return new Response(JSON.stringify(payload), {
    status,
    headers: {
      "content-type": "application/json",
    },
  });
}

function unauthorizedResponse(message: string): Response {
  return jsonResponse(401, { error: message });
}

function serverErrorResponse(message: string): Response {
  return jsonResponse(500, { error: message });
}

function isClientError(error: unknown): boolean {
  return isStructuredClientError(error);
}

function isPlainObject(value: unknown): value is Record<string, unknown> {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    return false;
  }

  const prototype = Object.getPrototypeOf(value);
  return prototype === Object.prototype || prototype === null;
}

async function requireAuth(request: Request): Promise<Response | null> {
  const expectedToken = process.env.CONVEX_SYNC_TOKEN;
  if (!expectedToken) {
    return serverErrorResponse("CONVEX_SYNC_TOKEN is not configured");
  }

  const authorization = request.headers.get("authorization") ?? "";
  if (!authorization.startsWith("Bearer ")) {
    return unauthorizedResponse("Missing bearer token");
  }

  const providedToken = authorization.slice("Bearer ".length).trim();
  if (providedToken !== expectedToken) {
    return unauthorizedResponse("Invalid bearer token");
  }

  return null;
}

async function readJson(request: Request): Promise<Record<string, unknown>> {
  const body = await request.text();
  if (body.trim() === "") {
    throw clientError(
      "missing_json_body",
      "Mutation request body must not be empty",
    );
  }

  const contentType = request.headers.get("content-type") ?? "";
  if (!contentType.includes("application/json")) {
    throw clientError(
      "invalid_content_type",
      "Mutation requests with a body must use application/json",
    );
  }

  let parsed: unknown;

  try {
    parsed = JSON.parse(body);
  } catch (error) {
    if (error instanceof SyntaxError) {
      throw clientError("invalid_json_body", "Request body must be valid JSON");
    }

    throw error;
  }

  if (!isPlainObject(parsed)) {
    throw clientError(
      "invalid_json_body_shape",
      "Mutation request body must be a JSON object",
    );
  }

  return parsed;
}

function readOptionalStringSearchParam(
  searchParams: URLSearchParams,
  name: string,
): string | undefined {
  const value = searchParams.get(name);
  if (value === null) {
    return undefined;
  }

  const normalized = value.trim();
  return normalized === "" ? undefined : normalized;
}

function readRequiredStringSearchParam(
  searchParams: URLSearchParams,
  name: string,
): string {
  const value = readOptionalStringSearchParam(searchParams, name);
  if (!value) {
    throw clientError(
      "missing_required_query_param",
      `Missing required ${name} query parameter`,
    );
  }

  return value;
}

function parseBooleanSearchParam(
  value: string | null,
  name: string,
): boolean | undefined {
  if (value === null) {
    return undefined;
  }

  if (value === "true" || value === "1") {
    return true;
  }

  if (value === "false" || value === "0") {
    return false;
  }

  throw clientError(
    "invalid_boolean_param",
    `Invalid ${name} value: ${value}. Expected one of true, false, 1, 0`,
  );
}

function buildSearchParamReader<TArgs extends Record<string, unknown>>(
  readArgs: (searchParams: URLSearchParams) => TArgs,
) {
  return (request: Request): TArgs => {
    const url = new URL(request.url);
    return readArgs(url.searchParams);
  };
}

const readListUserEventsArgs = buildSearchParamReader((searchParams) => ({
  lineUserId: readRequiredStringSearchParam(searchParams, "lineUserId"),
  includePast: parseBooleanSearchParam(searchParams.get("includePast"), "includePast"),
}));

const readListChatEventsArgs = buildSearchParamReader((searchParams) => ({
  sourceChatId: readRequiredStringSearchParam(searchParams, "sourceChatId"),
  includePast: parseBooleanSearchParam(searchParams.get("includePast"), "includePast"),
}));

const readGetDueRemindersArgs = buildSearchParamReader((searchParams) => {
  const lineUserId = readOptionalStringSearchParam(searchParams, "lineUserId");
  const sourceChatId = readOptionalStringSearchParam(searchParams, "sourceChatId");

  if (lineUserId && sourceChatId) {
    throw clientError(
      "mixed_query_scope",
      "getDueReminders accepts either lineUserId or sourceChatId, not both",
    );
  }

  return {
    today: readRequiredStringSearchParam(searchParams, "today"),
    lineUserId,
    sourceChatId,
  };
});

const readGetSettingArgs = buildSearchParamReader((searchParams) => ({
  key: readRequiredStringSearchParam(searchParams, "key"),
}));

function buildMutationRoute(
  name: string,
  reference: ReturnType<typeof makeFunctionReference<"mutation">>,
) {
  return httpActionGeneric(async (ctx, request) => {
    const authError = await requireAuth(request);
    if (authError) {
      return authError;
    }

    try {
      const body = await readJson(request);
      const result = await ctx.runMutation(reference, body);
      return jsonResponse(200, { route: name, data: result });
    } catch (error) {
      return jsonResponse(isClientError(error) ? 400 : 500, {
        route: name,
        error: getErrorMessage(error),
      });
    }
  });
}

function buildQueryRoute<TArgs extends Record<string, unknown>>(
  name: string,
  reference: ReturnType<typeof makeFunctionReference<"query">>,
  readArgs: (request: Request) => TArgs,
) {
  return httpActionGeneric(async (ctx, request) => {
    const authError = await requireAuth(request);
    if (authError) {
      return authError;
    }

    try {
      const args = readArgs(request);
      const result = await ctx.runQuery(reference, args);
      return jsonResponse(200, { route: name, data: result });
    } catch (error) {
      return jsonResponse(isClientError(error) ? 400 : 500, {
        route: name,
        error: getErrorMessage(error),
      });
    }
  });
}

function buildBodyQueryRoute(
  name: string,
  reference: ReturnType<typeof makeFunctionReference<"query">>,
) {
  return httpActionGeneric(async (ctx, request) => {
    const authError = await requireAuth(request);
    if (authError) {
      return authError;
    }

    try {
      const body = await readJson(request);
      const result = await ctx.runQuery(reference, body);
      return jsonResponse(200, { route: name, data: result });
    } catch (error) {
      return jsonResponse(isClientError(error) ? 400 : 500, {
        route: name,
        error: getErrorMessage(error),
      });
    }
  });
}

const upsertUserRef = makeFunctionReference<"mutation">("users:upsertUser");
const appendInteractionRef = makeFunctionReference<"mutation">("records:appendInteraction");
const createNoteRef = makeFunctionReference<"mutation">("records:createNote");
const createAssignmentRef = makeFunctionReference<"mutation">("records:createAssignment");
const createCharacterizationRef = makeFunctionReference<"mutation">(
  "records:createCharacterization",
);
const createDailyReportRef = makeFunctionReference<"mutation">("records:createDailyReport");
const createStaffMemoryItemRef = makeFunctionReference<"mutation">(
  "records:createStaffMemoryItem",
);
const upsertStaffMemoryItemRef = makeFunctionReference<"mutation">(
  "records:upsertStaffMemoryItem",
);
const listStaffMemoryItemsForWeekRef = makeFunctionReference<"query">(
  "records:listStaffMemoryItemsForWeek",
);
const upsertEventRef = makeFunctionReference<"mutation">("calendar:upsertEvent");
const deleteEventRef = makeFunctionReference<"mutation">("calendar:deleteEvent");
const markNotifiedRef = makeFunctionReference<"mutation">("calendar:markNotified");
const listUserEventsRef = makeFunctionReference<"query">("calendar:listUserEvents");
const listChatEventsRef = makeFunctionReference<"query">("calendar:listChatEvents");
const getDueRemindersRef = makeFunctionReference<"query">("calendar:getDueReminders");
const getSettingRef = makeFunctionReference<"query">("settings:getSetting");
const setSettingRef = makeFunctionReference<"mutation">("settings:setSetting");

// Mod Mode function references
const modModeUpsertRef = makeFunctionReference<"mutation">("modModeState:upsert");
const modModeGetByGroupRef = makeFunctionReference<"query">("modModeState:getByGroup");
const modModeDeactivateRef = makeFunctionReference<"mutation">("modModeState:deactivate");

const banListUpsertRef = makeFunctionReference<"mutation">("banList:upsert");
const banListGetByGroupUserRef = makeFunctionReference<"query">("banList:getByGroupUser");
const banListGetByGroupRef = makeFunctionReference<"query">("banList:getByGroup");
const banListRemoveRef = makeFunctionReference<"mutation">("banList:remove");

const userWarningsUpsertRef = makeFunctionReference<"mutation">("userWarnings:upsert");
const userWarningsGetByGroupUserRef = makeFunctionReference<"query">("userWarnings:getByGroupUser");
const userWarningsGetByGroupRef = makeFunctionReference<"query">("userWarnings:getByGroup");
const userWarningsResetWarningsRef = makeFunctionReference<"mutation">("userWarnings:resetWarnings");

http.route({
  path: "/records/upsertUser",
  method: "POST",
  handler: buildMutationRoute("/records/upsertUser", upsertUserRef),
});

http.route({
  path: "/records/appendInteraction",
  method: "POST",
  handler: buildMutationRoute("/records/appendInteraction", appendInteractionRef),
});

http.route({
  path: "/records/createNote",
  method: "POST",
  handler: buildMutationRoute("/records/createNote", createNoteRef),
});

http.route({
  path: "/records/createAssignment",
  method: "POST",
  handler: buildMutationRoute("/records/createAssignment", createAssignmentRef),
});

http.route({
  path: "/records/createCharacterization",
  method: "POST",
  handler: buildMutationRoute("/records/createCharacterization", createCharacterizationRef),
});

http.route({
  path: "/records/createDailyReport",
  method: "POST",
  handler: buildMutationRoute("/records/createDailyReport", createDailyReportRef),
});

http.route({
  path: "/records/createStaffMemoryItem",
  method: "POST",
  handler: buildMutationRoute(
    "/records/createStaffMemoryItem",
    createStaffMemoryItemRef,
  ),
});

http.route({
  path: "/records/upsertStaffMemoryItem",
  method: "POST",
  handler: buildMutationRoute(
    "/records/upsertStaffMemoryItem",
    upsertStaffMemoryItemRef,
  ),
});

http.route({
  path: "/records/listStaffMemoryItemsForWeek",
  method: "POST",
  handler: buildBodyQueryRoute(
    "/records/listStaffMemoryItemsForWeek",
    listStaffMemoryItemsForWeekRef,
  ),
});

http.route({
  path: "/calendar/upsertEvent",
  method: "POST",
  handler: buildMutationRoute("/calendar/upsertEvent", upsertEventRef),
});

http.route({
  path: "/calendar/deleteEvent",
  method: "POST",
  handler: buildMutationRoute("/calendar/deleteEvent", deleteEventRef),
});

http.route({
  path: "/calendar/listUserEvents",
  method: "GET",
  handler: buildQueryRoute(
    "/calendar/listUserEvents",
    listUserEventsRef,
    readListUserEventsArgs,
  ),
});

http.route({
  path: "/calendar/listChatEvents",
  method: "GET",
  handler: buildQueryRoute(
    "/calendar/listChatEvents",
    listChatEventsRef,
    readListChatEventsArgs,
  ),
});

http.route({
  path: "/calendar/getDueReminders",
  method: "GET",
  handler: buildQueryRoute(
    "/calendar/getDueReminders",
    getDueRemindersRef,
    readGetDueRemindersArgs,
  ),
});

http.route({
  path: "/calendar/markNotified",
  method: "POST",
  handler: buildMutationRoute("/calendar/markNotified", markNotifiedRef),
});

http.route({
  path: "/settings/get",
  method: "GET",
  handler: buildQueryRoute("/settings/get", getSettingRef, readGetSettingArgs),
});

http.route({
  path: "/settings/set",
  method: "POST",
  handler: buildMutationRoute("/settings/set", setSettingRef),
});

// Mod Mode routes
http.route({
  path: "/modModeState/upsert",
  method: "POST",
  handler: buildMutationRoute("/modModeState/upsert", modModeUpsertRef),
});

http.route({
  path: "/modModeState/getByGroup",
  method: "GET",
  handler: buildQueryRoute("/modModeState/getByGroup", modModeGetByGroupRef, (request: Request) => ({
    groupId: readRequiredStringSearchParam(new URL(request.url).searchParams, "groupId"),
  })),
});

http.route({
  path: "/modModeState/deactivate",
  method: "POST",
  handler: buildMutationRoute("/modModeState/deactivate", modModeDeactivateRef),
});

// Ban List routes
http.route({
  path: "/banList/upsert",
  method: "POST",
  handler: buildMutationRoute("/banList/upsert", banListUpsertRef),
});

http.route({
  path: "/banList/getByGroupUser",
  method: "GET",
  handler: buildQueryRoute("/banList/getByGroupUser", banListGetByGroupUserRef, (request: Request) => ({
    groupId: readRequiredStringSearchParam(new URL(request.url).searchParams, "groupId"),
    userId: readRequiredStringSearchParam(new URL(request.url).searchParams, "userId"),
  })),
});

http.route({
  path: "/banList/getByGroup",
  method: "GET",
  handler: buildQueryRoute("/banList/getByGroup", banListGetByGroupRef, (request: Request) => ({
    groupId: readRequiredStringSearchParam(new URL(request.url).searchParams, "groupId"),
  })),
});

http.route({
  path: "/banList/remove",
  method: "POST",
  handler: buildMutationRoute("/banList/remove", banListRemoveRef),
});

// User Warnings routes
http.route({
  path: "/userWarnings/upsert",
  method: "POST",
  handler: buildMutationRoute("/userWarnings/upsert", userWarningsUpsertRef),
});

http.route({
  path: "/userWarnings/getByGroupUser",
  method: "GET",
  handler: buildQueryRoute("/userWarnings/getByGroupUser", userWarningsGetByGroupUserRef, (request: Request) => ({
    groupId: readRequiredStringSearchParam(new URL(request.url).searchParams, "groupId"),
    userId: readRequiredStringSearchParam(new URL(request.url).searchParams, "userId"),
  })),
});

http.route({
  path: "/userWarnings/getByGroup",
  method: "GET",
  handler: buildQueryRoute("/userWarnings/getByGroup", userWarningsGetByGroupRef, (request: Request) => ({
    groupId: readRequiredStringSearchParam(new URL(request.url).searchParams, "groupId"),
  })),
});

http.route({
  path: "/userWarnings/resetWarnings",
  method: "POST",
  handler: buildMutationRoute("/userWarnings/resetWarnings", userWarningsResetWarningsRef),
});

http.route({
  path: "/health",
  method: "GET",
  handler: httpActionGeneric(async (_ctx, request) => {
    const authError = await requireAuth(request);
    if (authError) {
      return authError;
    }

    return jsonResponse(200, {
      ok: true,
      service: "convex-persistence",
      authenticated: true,
    });
  }),
});

export default http;