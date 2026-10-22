import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../services/api";
import type { Person } from "../types";

const STATUS_STYLE: Record<string, string> = {
  active: "bg-green-100 text-green-700",
  suspended: "bg-amber-100 text-amber-700",
  revoked: "bg-red-100 text-red-700",
};

export default function People() {
  const [people, setPeople] = useState<Person[]>([]);

  useEffect(() => {
    api.get<Person[]>("/api/people").then(
      (p) => setPeople(p),
      () => setPeople([])
    );
  }, []);

  return (
    <div className="p-6 max-w-5xl">
      <div className="flex items-center justify-between mb-4">
        <h1 className="text-2xl font-bold">Personas</h1>
        <Link
          to="/people/new"
          className="bg-brand-500 text-white px-4 py-2 rounded-lg text-sm"
        >
          + Registrar persona
        </Link>
      </div>
      <div className="rounded-xl border bg-white overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 text-slate-500">
            <tr className="text-left">
              <th className="py-2 px-4">Nombre</th>
              <th className="py-2 px-4">Estado</th>
              <th className="py-2 px-4">Vence</th>
              <th className="py-2 px-4">Registro</th>
              <th className="py-2 px-4" />
            </tr>
          </thead>
          <tbody>
            {people.map((p) => (
              <tr key={p.id} className="border-t">
                <td className="py-2 px-4 font-medium">{p.full_name}</td>
                <td className="py-2 px-4">
                  <span
                    className={`px-2 py-0.5 rounded-full text-xs ${
                      STATUS_STYLE[p.status] ?? ""
                    }`}
                  >
                    {p.status}
                  </span>
                </td>
                <td className="py-2 px-4">{p.expires_at?.slice(0, 10) ?? "—"}</td>
                <td className="py-2 px-4">{p.created_at?.slice(0, 10)}</td>
                <td className="py-2 px-4 text-right">
                  <Link
                    to={`/people/${p.id}`}
                    className="text-brand-600 hover:underline"
                  >
                    Ver detalles
                  </Link>
                </td>
              </tr>
            ))}
            {people.length === 0 && (
              <tr>
                <td colSpan={5} className="py-8 text-center text-slate-500">
                  Todavía no hay personas registradas
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
