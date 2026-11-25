export class ApiError extends Error {
  constructor(code) {
    super(code);
    this.code = code;
  }
}

export function client(getToken, onExpired) {
  return async function request(path, {method = "GET", data, signal} = {}) {
    const timeout = AbortSignal.timeout(20000);
    try {
      const response = await fetch(path, {
        method,
        credentials: "same-origin",
        cache: "no-store",
        headers: data === undefined ? {Accept: "application/json"} :
          {Accept: "application/json", "Content-Type": "application/json", "X-CSRF-Token": getToken()},
        body: data === undefined ? undefined : JSON.stringify(data),
        signal: signal ? AbortSignal.any([signal, timeout]) : timeout,
      });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) {
        if (response.status === 401 && path !== "/api/login" && payload.error === "unauthorized") onExpired();
        throw new ApiError(payload.error ?? "server_error");
      }
      return payload;
    } catch (error) {
      if (error instanceof ApiError || signal?.aborted) throw error;
      throw new ApiError(timeout.aborted ? "timeout" : "network");
    }
  };
}
