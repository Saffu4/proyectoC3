import { useEffect, useState } from "react";
import { api } from "../services/api";
import type { Role } from "../types";

const AVAILABLE_PERMISSIONS = ["access.granted", "panel.admin"];

export default function Roles() {
  const [roles, setRoles] = useState<Role[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = () => {
    api.get<Role[]>("/api/roles").then(setRoles, (e) => setError(e.message));
  };
  useEffect(load, []);

  async function togglePermission(role: Role, code: string) {
    setBusy(true);
    try {
      const permissions = role.permissions.includes(code)
        ? role.permissions.filter((p) => p !== code)
        : [...role.permissions, code];
      await api.patch(`/api/roles/${role.id}`, { permissions });
      load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Error");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="p-6 max-w-3xl">
      <h1 className="text-2xl font-bold mb-4">Roles y permisos</h1>
      {error && <div className="bg-red-50 text-red-700 p-3 rounded-lg text-sm">{error}</div>}
      <p className="text-xs text-slate-500 mb-4">
        Los cambios surten inmediata en la siguiente comprobación de acceso, con o sin
        conexión remota. No se concede rol administrativo por coincidencia facial.
      </p>
      <div className="space-y-4">
        {roles.map((role) => (
          <div key={role.id} className="rounded-xl border bg-white p-4">
            <div className="flex items-center justify-between">
              <div>
                <div className="font-semibold">{role.name}</div>
                <div className="text-slate-500 text-sm">{role.description}</div>
              </div>
              {role.name === "admin" && (
                <span className="text-xs bg-slate-100 px-2 py-1 rounded-full">
                  rol protegido
                </span>
              )}
            </div>
            <div className="mt-3 flex flex-wrap gap-2">
              {AVAILABLE_PERMISSIONS.map((code) => {
                const on = role.permissions.includes(code);
                return (
                  <button
                    key={code}
                    disabled={busy}
                    onClick={() => togglePermission(role, code)}
                    className={`text-xs px-3 py-1.5 rounded-full border ${
                      on ? "bg-brand-50 border-brand-500 text-brand-600" : "text-slate-500"
                    }`}
                  >
                    {on ? "✓ " : "+ "}
                    {code}
                  </button>
                );
              })}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
