/* eslint-disable */
/**
 * Generated `api` utility.
 *
 * THIS CODE IS AUTOMATICALLY GENERATED.
 *
 * To regenerate, run `npx convex dev`.
 * @module
 */

import type * as banList from "../banList.js";
import type * as calendar from "../calendar.js";
import type * as calendar_helpers from "../calendar_helpers.js";
import type * as client_errors from "../client_errors.js";
import type * as debriefSessions from "../debriefSessions.js";
import type * as http from "../http.js";
import type * as modModeState from "../modModeState.js";
import type * as placeholder from "../placeholder.js";
import type * as records from "../records.js";
import type * as settings from "../settings.js";
import type * as userWarnings from "../userWarnings.js";
import type * as users from "../users.js";

import type {
  ApiFromModules,
  FilterApi,
  FunctionReference,
} from "convex/server";

declare const fullApi: ApiFromModules<{
  banList: typeof banList;
  calendar: typeof calendar;
  calendar_helpers: typeof calendar_helpers;
  client_errors: typeof client_errors;
  debriefSessions: typeof debriefSessions;
  http: typeof http;
  modModeState: typeof modModeState;
  placeholder: typeof placeholder;
  records: typeof records;
  settings: typeof settings;
  userWarnings: typeof userWarnings;
  users: typeof users;
}>;

/**
 * A utility for referencing Convex functions in your app's public API.
 *
 * Usage:
 * ```js
 * const myFunctionReference = api.myModule.myFunction;
 * ```
 */
export declare const api: FilterApi<
  typeof fullApi,
  FunctionReference<any, "public">
>;

/**
 * A utility for referencing Convex functions in your app's internal API.
 *
 * Usage:
 * ```js
 * const myFunctionReference = internal.myModule.myFunction;
 * ```
 */
export declare const internal: FilterApi<
  typeof fullApi,
  FunctionReference<any, "internal">
>;

export declare const components: {};
