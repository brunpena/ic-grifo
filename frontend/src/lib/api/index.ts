export { api, apiUrl, API_URL, unwrap } from "./client";
export { ApiError, errorMessage } from "./errors";
export type { components, paths } from "./schema";

import type { components } from "./schema";

export type Schemas = components["schemas"];
export type HealthResponse = Schemas["HealthResponse"];
export type User = Schemas["UserOut"];
