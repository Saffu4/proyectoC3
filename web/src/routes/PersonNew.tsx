import { useState, FormEvent } from "react";
import { useNavigate, Link } from "react-router-dom";
import { api } from "../services/api";

export default function PersonNew() {
  const navigate = useNavigate();
  const [fullName, setFullName] = useState("");
  const [documentId, setDocumentId] = useState("");
  const [expiresAt, setExpiresAt] = useState("");
  const [role, setRole] = useState("user");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const data = await api.post<{ id: string }>("/api/people", {
        full_name: fullName,
        document_id: documentId || undefined,
        expires_at: expiresAt || undefined,
        roles: [role],
      });
      navigate(`/people/${data.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "No se pudo registrar");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="p-6 max-w-md">
      <Link to="/people" className="text-sm text-brand-600 hover:underline">
        ← Personas
      </Link>
      <h1 className="text-2xl font-bold my-4">Registrar persona</h1>
      <form onSubmit={onSubmit} className="space-y-4 rounded-xl border bg-white p-6">
        <div>
          <label className="block text-sm font-medium">Nombre completo</label>
          <input
            value={fullName}
            onChange={(e) => setFullName(e.target.value)}
            required
            className="mt-1 border rounded-lg px-3 py-2 w-full"
          />
        </div>
        <div>
          <label className="block text-sm font-medium">Identificador / documento</label>
          <input
            value={documentId}
            onChange={(e) => setDocumentId(e.target.value)}
            className="mt-1 border rounded-lg px-3 py-2 w-full"
          />
        </div>
        <div>
          <label className="block text-sm font-medium">Vigencia (opcional)</label>
          <input
            type="date"
            value={expiresAt}
            onChange={(e) => setExpiresAt(e.target.value)}
            className="mt-1 border rounded-lg px-3 py-2 w-full"
          />
        </div>
        <div>
          <label className="block text-sm font-medium">Rol</label>
          <select
            value={role}
            onChange={(e) => setRole(e.target.value)}
            className="mt-1 border rounded-lg px-3 py-2 w-full"
          >
            <option value="user">user · acceso autorizado</option>
            <option value="admin">admin · administrativo</option>
          </select>
        </div>
        {error && (
          <div className="text-sm bg-red-50 text-red-700 rounded-lg p-3">{error}</div>
        )}
        <div className="flex items-center justify-between">
          <p className="text-xs text-slate-500">
            Tras crearla, en el detalle se capturan los rostros y se entrena el modelo.
          </p>
          <button
            type="submit"
            disabled={busy}
            className="bg-brand-500 text-white px-4 py-2 rounded-lg disabled:opacity-50"
          >
            {busy ? "Guardando…" : "Crear persona"}
          </button>
        </div>
      </form>
    </div>
  );
}
