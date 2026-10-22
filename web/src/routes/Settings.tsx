import { useEffect, useState } from "react";
import { api } from "../services/api";

export default function Settings() {
  const [settings, setSettings] = useState<Record<string, string>>({});
  const [editKey, setEditKey] = useState<string | null>(null);
  const [editValue, setEditValue] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const load = () =>
    api
      .get<Record<string, string>>("/api/settings")
      .then(setSettings, (e) => setError(e.message));
  useEffect(load, []);

  async function save(key: string) {
    try {
      await api.patch("/api/settings", { [key]: editValue });
      setMessage(`Configuración actualizada: ${key}`);
      setEditKey(null);
      load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Error");
    }
  }

  async function syncNow() {
    setError(null);
    try {
      const r = await api.post<Record<string, unknown>>("/api/sync/now");
      setMessage(`Sincronización: ${r.status}`);
      load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Error");
    }
  }

  const entries = Object.entries(settings).filter(
    ([k]) => k !== "kiosk_token" && k !== "device_id"
  );

  return (
    <div className="p-6 max-w-2xl">
      <h1 className="text-2xl font-bold mb-4">Configuración del dispositivo</h1>
      {message && <div className="bg-green-50 text-green-700 p-3 rounded-lg text-sm mb-4">{message}</div>}
      {error && <div className="bg-red-50 text-red-700 p-3 rounded-lg text-sm mb-4">{error}</div>}
      <div className="rounded-xl border bg-white divide-y">
        {entries.map(([k, v]) => (
          <div key={k} className="p-3 flex items-center gap-3 text-sm">
            <div className="w-48 shrink-0 font-mono">{k}</div>
            {editKey === k ? (
              <>
                <input
                  value={editValue}
                  onChange={(e) => setEditValue(e.target.value)}
                  className="flex-1 border rounded px-2 py-1"
                />
                <button onClick={() => save(k)} className="text-brand-600">
                  Guardar
                </button>
                <button onClick={() => setEditKey(null)} className="text-slate-500">
                  Cancelar
                </button>
              </>
            ) : (
              <>
                <div className="flex-1 truncate text-slate-600">{v}</div>
                <button
                  className="text-brand-600"
                  onClick={() => {
                    setEditKey(k);
                    setEditValue(v);
                  }}
                >
                  Editar
                </button>
              </>
            )}
          </div>
        ))}
        {entries.length === 0 && (
          <div className="p-4 text-slate-500">Sin configuraciones guardadas.</div>
        )}
      </div>
      <button
        onClick={syncNow}
        className="mt-6 bg-brand-500 text-white px-4 py-2 rounded-lg text-sm"
      >
        Sincronizar ahora
      </button>
      <p className="text-xs text-slate-500 mt-4">
        El id de dispositivo y el token de quiosco no son editables desde el panel.
        Rutas de datos, umbral LBPH y parámetros de cámara viven en <code>.env</code> del
        servicio (no en esta base de datos).
      </p>
    </div>
  );
}
