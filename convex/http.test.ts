import test from "node:test";
import assert from "node:assert/strict";
import { ConvexError } from "convex/values";

import http from "./http";

type RouteHandler = (ctx: unknown, request: Request) => Promise<Response>;

function getRoute(path: string, method: "GET" | "POST") {
  const match = http.lookup(path, method);
  assert.ok(match, `Expected route ${method} ${path}`);
  return match[0] as unknown as RouteHandler;
}

test("health route returns 401 when bearer token is missing", async () => {
  process.env.CONVEX_SYNC_TOKEN = "secret";
  const route = getRoute("/health", "GET");

  const response = await route({} as never, new Request("https://example.test/health"));

  assert.equal(response.status, 401);
  assert.deepEqual(await response.json(), { error: "Missing bearer token" });
});

test("mutation route maps structured ConvexError payloads to 400", async () => {
  process.env.CONVEX_SYNC_TOKEN = "secret";
  const route = getRoute("/calendar/upsertEvent", "POST");

  const response = await route(
    {
      runMutation: async () => {
        throw new ConvexError({
          kind: "client_error",
          status: 400,
          code: "invalid_iso_date",
          message: "Invalid eventDate: 2026-02-30",
        });
      },
    } as never,
    new Request("https://example.test/calendar/upsertEvent", {
      method: "POST",
      headers: {
        authorization: "Bearer secret",
        "content-type": "application/json",
      },
      body: JSON.stringify({}),
    }),
  );

  assert.equal(response.status, 400);
  assert.deepEqual(await response.json(), {
    route: "/calendar/upsertEvent",
    error: "Invalid eventDate: 2026-02-30",
  });
});

test("query route maps unexpected errors to 500 even if the message starts with Invalid", async () => {
  process.env.CONVEX_SYNC_TOKEN = "secret";
  const route = getRoute("/calendar/listUserEvents", "GET");

  const response = await route(
    {
      runQuery: async () => {
        throw new Error("Invalid but unexpected infrastructure failure");
      },
    } as never,
    new Request("https://example.test/calendar/listUserEvents?lineUserId=user_1", {
      headers: {
        authorization: "Bearer secret",
      },
    }),
  );

  assert.equal(response.status, 500);
  assert.deepEqual(await response.json(), {
    route: "/calendar/listUserEvents",
    error: "Invalid but unexpected infrastructure failure",
  });
});

test("settings get only forwards the declared key arg", async () => {
  process.env.CONVEX_SYNC_TOKEN = "secret";
  const route = getRoute("/settings/get", "GET");
  let receivedArgs: unknown;

  const response = await route(
    {
      runQuery: async (_reference: unknown, args: unknown) => {
        receivedArgs = args;
        return { ok: true };
      },
    } as never,
    new Request(
      "https://example.test/settings/get?key=timezone&lineUserId=user_1&sourceChatId=chat_1&today=2026-06-15&includePast=true",
      {
        headers: {
          authorization: "Bearer secret",
        },
      },
    ),
  );

  assert.equal(response.status, 200);
  assert.deepEqual(receivedArgs, {
    key: "timezone",
  });
});

test("settings get rejects a missing required key param", async () => {
  process.env.CONVEX_SYNC_TOKEN = "secret";
  const route = getRoute("/settings/get", "GET");

  const response = await route(
    {
      runQuery: async () => {
        throw new Error("route should reject missing key before runQuery");
      },
    } as never,
    new Request("https://example.test/settings/get", {
      headers: {
        authorization: "Bearer secret",
      },
    }),
  );

  assert.equal(response.status, 400);
  assert.deepEqual(await response.json(), {
    route: "/settings/get",
    error: "Missing required key query parameter",
  });
});

test("list user events route only forwards user list args", async () => {
  process.env.CONVEX_SYNC_TOKEN = "secret";
  const route = getRoute("/calendar/listUserEvents", "GET");
  let receivedArgs: unknown;

  const response = await route(
    {
      runQuery: async (_reference: unknown, args: unknown) => {
        receivedArgs = args;
        return [];
      },
    } as never,
    new Request(
      "https://example.test/calendar/listUserEvents?lineUserId=user_1&includePast=1&sourceChatId=chat_1&today=2026-06-15&key=timezone",
      {
        headers: {
          authorization: "Bearer secret",
        },
      },
    ),
  );

  assert.equal(response.status, 200);
  assert.deepEqual(receivedArgs, {
    lineUserId: "user_1",
    includePast: true,
  });
});

test("list user events route rejects malformed includePast values", async () => {
  process.env.CONVEX_SYNC_TOKEN = "secret";
  const route = getRoute("/calendar/listUserEvents", "GET");

  const response = await route(
    {
      runQuery: async () => {
        throw new Error("route should reject malformed includePast before runQuery");
      },
    } as never,
    new Request(
      "https://example.test/calendar/listUserEvents?lineUserId=user_1&includePast=maybe",
      {
        headers: {
          authorization: "Bearer secret",
        },
      },
    ),
  );

  assert.equal(response.status, 400);
  assert.deepEqual(await response.json(), {
    route: "/calendar/listUserEvents",
    error: "Invalid includePast value: maybe. Expected one of true, false, 1, 0",
  });
});

test("list chat events route only forwards chat list args", async () => {
  process.env.CONVEX_SYNC_TOKEN = "secret";
  const route = getRoute("/calendar/listChatEvents", "GET");
  let receivedArgs: unknown;

  const response = await route(
    {
      runQuery: async (_reference: unknown, args: unknown) => {
        receivedArgs = args;
        return [];
      },
    } as never,
    new Request(
      "https://example.test/calendar/listChatEvents?sourceChatId=chat_1&includePast=true&lineUserId=user_1&today=2026-06-15&key=timezone",
      {
        headers: {
          authorization: "Bearer secret",
        },
      },
    ),
  );

  assert.equal(response.status, 200);
  assert.deepEqual(receivedArgs, {
    sourceChatId: "chat_1",
    includePast: true,
  });
});

test("due reminders route only forwards reminder query args", async () => {
  process.env.CONVEX_SYNC_TOKEN = "secret";
  const route = getRoute("/calendar/getDueReminders", "GET");
  let receivedArgs: unknown;

  const response = await route(
    {
      runQuery: async (_reference: unknown, args: unknown) => {
        receivedArgs = args;
        return [];
      },
    } as never,
    new Request(
      "https://example.test/calendar/getDueReminders?today=2026-06-15&lineUserId=user_1&includePast=true&key=timezone",
      {
        headers: {
          authorization: "Bearer secret",
        },
      },
    ),
  );

  assert.equal(response.status, 200);
  assert.deepEqual(receivedArgs, {
    today: "2026-06-15",
    lineUserId: "user_1",
    sourceChatId: undefined,
  });
});

test("due reminders route rejects mixed user and chat scope at the HTTP boundary", async () => {
  process.env.CONVEX_SYNC_TOKEN = "secret";
  const route = getRoute("/calendar/getDueReminders", "GET");

  const response = await route(
    {
      runQuery: async () => {
        throw new Error("route should reject mixed reminder scope before runQuery");
      },
    } as never,
    new Request(
      "https://example.test/calendar/getDueReminders?today=2026-06-15&lineUserId=user_1&sourceChatId=chat_1",
      {
        headers: {
          authorization: "Bearer secret",
        },
      },
    ),
  );

  assert.equal(response.status, 400);
  assert.deepEqual(await response.json(), {
    route: "/calendar/getDueReminders",
    error: "getDueReminders accepts either lineUserId or sourceChatId, not both",
  });
});

test("mutation routes reject non-JSON request bodies instead of treating them as empty", async () => {
  process.env.CONVEX_SYNC_TOKEN = "secret";
  const route = getRoute("/calendar/upsertEvent", "POST");

  const response = await route(
    {
      runMutation: async () => {
        throw new Error("route should reject non-JSON mutation bodies before runMutation");
      },
    } as never,
    new Request("https://example.test/calendar/upsertEvent", {
      method: "POST",
      headers: {
        authorization: "Bearer secret",
        "content-type": "text/plain",
      },
      body: "not json",
    }),
  );

  assert.equal(response.status, 400);
  assert.deepEqual(await response.json(), {
    route: "/calendar/upsertEvent",
    error: "Mutation requests with a body must use application/json",
  });
});

test("mutation routes reject empty request bodies at the HTTP boundary", async () => {
  process.env.CONVEX_SYNC_TOKEN = "secret";
  const route = getRoute("/calendar/upsertEvent", "POST");
  let runMutationCalled = false;

  const response = await route(
    {
      runMutation: async () => {
        runMutationCalled = true;
        throw new Error("route should reject empty mutation bodies before runMutation");
      },
    } as never,
    new Request("https://example.test/calendar/upsertEvent", {
      method: "POST",
      headers: {
        authorization: "Bearer secret",
      },
    }),
  );

  assert.equal(runMutationCalled, false);
  assert.equal(response.status, 400);
  assert.deepEqual(await response.json(), {
    route: "/calendar/upsertEvent",
    error: "Mutation request body must not be empty",
  });
});

test("mutation routes reject malformed JSON request bodies as client errors", async () => {
  process.env.CONVEX_SYNC_TOKEN = "secret";
  const route = getRoute("/calendar/upsertEvent", "POST");

  const response = await route(
    {
      runMutation: async () => {
        throw new Error("route should reject malformed JSON before runMutation");
      },
    } as never,
    new Request("https://example.test/calendar/upsertEvent", {
      method: "POST",
      headers: {
        authorization: "Bearer secret",
        "content-type": "application/json",
      },
      body: "{",
    }),
  );

  assert.equal(response.status, 400);
  assert.deepEqual(await response.json(), {
    route: "/calendar/upsertEvent",
    error: "Request body must be valid JSON",
  });
});

test("mutation routes reject non-object JSON bodies", async (t) => {
  process.env.CONVEX_SYNC_TOKEN = "secret";
  const route = getRoute("/calendar/upsertEvent", "POST");

  const cases = [
    { name: "null", body: "null" },
    { name: "array", body: "[]" },
    { name: "string", body: '"event"' },
    { name: "number", body: "123" },
    { name: "boolean", body: "true" },
  ];

  for (const testCase of cases) {
    await t.test(testCase.name, async () => {
      const response = await route(
        {
          runMutation: async () => {
            throw new Error("route should reject non-object JSON before runMutation");
          },
        } as never,
        new Request("https://example.test/calendar/upsertEvent", {
          method: "POST",
          headers: {
            authorization: "Bearer secret",
            "content-type": "application/json",
          },
          body: testCase.body,
        }),
      );

      assert.equal(response.status, 400);
      assert.deepEqual(await response.json(), {
        route: "/calendar/upsertEvent",
        error: "Mutation request body must be a JSON object",
      });
    });
  }
});

test("downstream SyntaxError still returns 500", async () => {
  process.env.CONVEX_SYNC_TOKEN = "secret";
  const route = getRoute("/calendar/listUserEvents", "GET");

  const response = await route(
    {
      runQuery: async () => {
        throw new SyntaxError("Unexpected token from downstream query");
      },
    } as never,
    new Request("https://example.test/calendar/listUserEvents?lineUserId=user_1", {
      headers: {
        authorization: "Bearer secret",
      },
    }),
  );

  assert.equal(response.status, 500);
  assert.deepEqual(await response.json(), {
    route: "/calendar/listUserEvents",
    error: "Unexpected token from downstream query",
  });
});