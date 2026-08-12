import { ConvexError } from "convex/values";

export const CLIENT_ERROR_KIND = "client_error";
export const CLIENT_ERROR_STATUS = 400;

export type ClientErrorCode =
  | "ambiguous_legacy_match"
  | "invalid_content_type"
  | "invalid_boolean_param"
  | "invalid_json_body"
  | "invalid_json_body_shape"
  | "invalid_iso_date"
  | "missing_json_body"
  | "missing_required_query_param"
  | "missing_query_scope"
  | "mixed_query_scope"
  | "missing_event"
  | "reminder_day_mismatch"
  | "reminder_day_not_configured"
  | "unknown_event_id";

export type ClientErrorData = {
  kind: typeof CLIENT_ERROR_KIND;
  status: typeof CLIENT_ERROR_STATUS;
  code: ClientErrorCode;
  message: string;
};

export function clientError(
  code: ClientErrorCode,
  message: string,
): ConvexError<ClientErrorData> {
  return new ConvexError({
    kind: CLIENT_ERROR_KIND,
    status: CLIENT_ERROR_STATUS,
    code,
    message,
  });
}

export function isClientErrorData(value: unknown): value is ClientErrorData {
  if (!value || typeof value !== "object") {
    return false;
  }

  const candidate = value as Partial<ClientErrorData>;
  return (
    candidate.kind === CLIENT_ERROR_KIND &&
    candidate.status === CLIENT_ERROR_STATUS &&
    typeof candidate.code === "string" &&
    typeof candidate.message === "string"
  );
}

export function isStructuredClientError(
  error: unknown,
): error is ConvexError<ClientErrorData> {
  return error instanceof ConvexError && isClientErrorData(error.data);
}

export function getErrorMessage(error: unknown): string {
  if (isStructuredClientError(error)) {
    return error.data.message;
  }

  if (error instanceof Error) {
    return error.message;
  }

  return String(error);
}