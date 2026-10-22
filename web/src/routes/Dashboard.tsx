import { useEffect, useState } from "react";
import { api } from "../services/api";
import type { DeviceStatus } from "../types";

function Card({ label, value, warn }: { label: string; value: string; warn?: boolean }) {
  return (
    <div className="rounded-xl border bg-white p-4">
      <div className="text-sm text-slate-500">{label}</div>
      <div className={`text-2xl font-semibold ${warn ? "text-amber-600" : ""}`}>
        {value}
      </div>
    </div>
  );
}

export default function Dashboard() {
  const [status, setStatus] = useState<DeviceStatus | null>(null);

  useEffect(() => {
    let live = true;
    api.get<DeviceStatus>("/api/device/status").then(
      (s) => live && setStatus(s),
      () => live && setStatus(null)
    );
    const t = setInterval(() => {
      api.get<DeviceStatus>("/api/device/status").then(
        (s) => live && setStatus(s),
        () => {}
      );
    }, 10000);
    return () => {
      live = false;
      clearInterval(t);
    };
  }, []);

  if (!status) {
    return <div className="p-6 text-slate-500">Sincronizando estado del dispositivo…</div>;
  }

  return (
    <div className="p-6 space-y-6 max-w-5xl">
      <h1 className="text-2xl font-bold">Dashboard</h1>
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        <Card label="Accesos concedidos" value={String(status.events.granted)} />
        <Card label="Accesos denegados" value={String(status.events.denied)} />
        <Card label="Eventos sin sincronizar" value={String(status.pending_events)} />
        <Card
          label="Rostros entrenados"
          value={String(status.model.faces_trained)}
        />
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <div className="rounded-xl border bg-white p-4">
          <div className="font-semibold mb-2">Dispositivo</div>
          <dl className="text-sm grid grid-cols-3 gap-2">
            <dt className="text-slate-500">ID</dt>
            <dd className="col-span-2 truncate">{status.device_id}</dd>
            <dt className="text-slate-500">Cámara</dt>
            <dd className="col-span-2">
              {status.camera.available ? (
                <span className="text-green-600">Disponible</span>
              ) : (
                <span className="text-red-600">Desconectada</span>
              )}
            </dd>
            <dt className="text-slate-500">Modelo LBPH</dt>
            <dd className="col-span-2">
              {status.model.trained
                ? `Entrenado (umbral ${status.model.threshold})`
                : <span className="text-red-600">No entrenado</span>}
            </dd>
          </dl>
        </div>
        <div className="rounded-xl border bg-white p-4">
          <div className="font-semibold mb-2">Sincronización</div>
          <dl className="text-sm grid grid-cols-3 gap-2">
            <dt className="text-slate-500">Estado</dt>
            <dd className="col-span-2">
              {status.sync.enabled ? "Habilitada" : "Sin Supabase (modo local)"}
            </dd>
            <dt className="text-slate-500">Último sync</dt>
            <dd className="col-span-2">{status.sync.last_policy_sync ?? "—"}</dd>
            <dt className="text-slate-500">Política</dt>
            <dd className="col-span-2">
              {status.sync.stale ? (
                <span className="text-amber-600">
                  Copia vencida o ausente: decisiones privilegiadas bloqueadas
                </span>
              ) : (
                "Vigente"
              )}
            </dd>
          </dl>
        </div>
      </div>
      <p className="text-xs text-slate-500">
        Un permiso revocado en el servidor nunca es reactivado por la copia local aunque
        la Pi haya estado sin conexión. Si el dispositivo se conecta por horas sin
        sincronizar, el panel mostrará "copias vencidas" y no avanzará en acceso
        privilegiado.
      </p>
    </div>
  );
}
