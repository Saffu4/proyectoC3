/** Cliente HTTP para la API del dispositivo. El token NO se envía a terceros
 *  y se guarda en memoria de la pestaña (sessionStorage borrable por cierre). */
const TOKEN_KEY = "proyectoc3_token";

export class ApiError extends Error {
  status: number;
  code: string;
  constructor(status: number, code: string, message: string) {
    super(message);
    this.status = status;
    this.code = code;
  }
}

export function getToken(): string | null {
  try {
    return sessionStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

export function setToken(token: string | null) {
  try {
    if (token) sessionStorage.setItem(TOKEN_KEY, token);
    else sessionStorage.removeItem(TOKEN_KEY);
  } catch {
    /* modo privado / sin storage: la sesión vive solo en memoria */
  }
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers: Record<string, string> = {
    ...(options.headers as Record<string, string> | undefined),
  };
  if (options.body !== undefined && !headers["Content-Type"]) {
    headers["Content-Type"] = "application/json";
  }
  const token = getToken();
  if (token) headers["Authorization"] = `Bearer ${token}`;

  let resp: Response;
  try {
    resp = await fetch(path, { ...options, headers, credentials: "omit" });
  } catch (e) {
    throw new ApiError(0, "network", "No se pudo conectar con el dispositivo");
  }
  if (resp.status === 401) {
    setToken(null);
  }
  const text = await resp.text();
  const data = text ? JSON.parse(text) : {};
  if (!resp.ok) {
    throw new ApiError(
      resp.status,
      data.error ?? "error",
      data.message ?? "Error desconocido"
    );
  }
  return data as T;
}

export const api = {
  get: <T,>(path: string) => request<T>(path),
  post: <T,>(path: string, body?: unknown) =>
    request<T>(path, { method: "POST", body: body === undefined ? undefined : JSON.stringify(body) }),
  patch: <T,>(path: string, body?: unknown) =>
    request<T>(path, { method: "PATCH", body: JSON.stringify(body ?? {}) }),
  delete: <T,>(path: string) => request<T>(path, { method: "DELETE" }),
};
