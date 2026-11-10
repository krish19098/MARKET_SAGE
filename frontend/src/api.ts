// Thin API client. Session is an httpOnly cookie; no secrets are stored in the frontend.
export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

export async function api<T = any>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`/api${path}`, {
    credentials: "same-origin",
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!res.ok) {
    let msg = res.statusText;
    try {
      const body = await res.json();
      msg = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail ?? body);
    } catch {
      /* non-JSON error */
    }
    throw new ApiError(res.status, msg);
  }
  return res.json() as Promise<T>;
}

export const post = <T = any>(path: string, body: unknown) => api<T>(path, { method: "POST", body: JSON.stringify(body) });

function urlB64ToUint8Array(base64: string): Uint8Array {
  const padding = "=".repeat((4 - (base64.length % 4)) % 4);
  const raw = atob((base64 + padding).replace(/-/g, "+").replace(/_/g, "/"));
  return Uint8Array.from(raw, (c) => c.charCodeAt(0));
}

/** Subscribe this device to Web Push (where supported). Returns a human-readable status. */
export async function enablePush(): Promise<string> {
  if (!("serviceWorker" in navigator) || !("PushManager" in window)) return "Push notifications are not supported on this browser.";
  const { publicKey, enabled } = await api<{ publicKey: string | null; enabled: boolean }>("/push/public-key");
  if (!enabled || !publicKey) return "Push is not configured on the server (VAPID keys missing). Alerts remain in the in-app history.";
  const perm = await Notification.requestPermission();
  if (perm !== "granted") return "Notification permission was not granted.";
  const reg = await navigator.serviceWorker.ready;
  const sub = await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: urlB64ToUint8Array(publicKey) });
  const json = sub.toJSON();
  await post("/push/subscribe", { endpoint: json.endpoint, keys: json.keys });
  return "Push alerts enabled on this device. Delivery is best-effort; the in-app alert history is the reliable record.";
}
