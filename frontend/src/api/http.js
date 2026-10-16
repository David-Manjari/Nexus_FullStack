import { API_BASE_URL } from "./config";

// All browser API calls include the Flask session cookie and surface JSON errors.
export async function apiRequest(path, options = {}) {
  const headers = new Headers(options.headers ?? {});
  let body = options.body;

  if (body !== undefined && !(typeof FormData !== "undefined" && body instanceof FormData)) {
    headers.set("Content-Type", "application/json");
    body = JSON.stringify(body);
  }

  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    body,
    headers,
    credentials: "include",
  });
  const contentType = response.headers.get("content-type") ?? "";
  const result = contentType.includes("application/json")
    ? await response.json()
    : await response.text();

  if (!response.ok) {
    throw new Error(
      (typeof result === "object" && (result.error || result.message)) ||
        `Request failed (${response.status}).`
    );
  }

  return result;
}