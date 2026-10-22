import { useEffect, useState } from "react";
import { api } from "../services/api";
import type { AccessEvent } from "../types";

export default function AccessHistory() {
  const [events, setEvents] = useState<AccessEvent[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.get<AccessEvent[]>("/api/access-events?limit=200").then(
      (e) => setEvents(e),
      (e) => setError(e.message)
    );
  }, []);

  return (
    <div className="p-6 max-w-5xl">
      <h1 className="text-2xl font-bold mb-4">Historial de accesos</h1>
      {error && <div className="bg-red-50 text-red-700 p-3 rounded-lg text-sm">{error}</div>}
      <div className="rounded-xl border bg-white overflow-x-auto">
        <table className="w-full text-sm min-w-[640px]">
          <thead className="bg-slate-50 text-slate-500">
            <tr className="text-left">
              <th className="py-2 px-4">Fecha/Hora</th>
              <th className="py-2 px-4">Persona</th>
              <th className="py-2 px-4">Resultado</th>
              <th className="py-2 px-4">Categoría</th>
              <th className="py-2 px-4">Dist. LBPH</th>
            </tr>
          </thead>
          <tbody>
            {events.map((e) => (
              <tr key={e.event_id} className="border-t">
                <td className="py-2 px-4 whitespace-nowrap">{e.timestamp?.slice(0, 19)}</td>
                <td className="py-2 px-4">{e.full_name ?? <em className="text-slate-400">desconocida</em>}</td>
                <td className="py-2 px-4">
                  <span className={`px-2 py-0.5 rounded-full text-xs ${
                    e.result === "granted" ? "bg-green-100 text-green-700" : "bg-red-100 text-red-700"
                  }`}>
                    {e.result}
                  </span>
                </td>
                <td className="py-2 px-4">{e.category ?? "—"}</td>
                <td className="py-2 px-4">{e.confidence != null ? e.confidence.toFixed(1) : "—"}</td>
              </tr>
            ))}
            {events.length === 0 && (
              <tr><td colSpan={5} className="py-8 text-center text-slate-500">Sin eventos registrados</td></tr>
            )}
          </tbody>
        </table>
      </div>
      <p className="text-xs text-slate-500 mt-3">
        "Dist. LBPH" es la distancia del modelo (menor = más cercano), no una probabilidad.
        Solo útil para comparar contra el umbral calibrado.
      </p>
    </div>
  );
}
