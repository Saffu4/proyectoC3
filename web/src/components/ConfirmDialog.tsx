export function ConfirmDialog({
  title,
  description,
  onConfirm,
  onCancel,
  danger,
}: {
  title: string;
  description: string;
  onConfirm: () => void;
  onCancel: () => void;
  danger?: boolean;
}) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div className="bg-white rounded-xl p-6 max-w-md w-full shadow-xl">
        <h2 className="font-semibold text-lg">{title}</h2>
        <p className="text-slate-600 text-sm mt-2">{description}</p>
        <div className="mt-6 flex justify-end gap-2">
          <button className="px-4 py-2 rounded-lg border" onClick={onCancel}>
            Cancelar
          </button>
          <button
            className={`px-4 py-2 rounded-lg text-white ${
              danger ? "bg-red-600" : "bg-brand-500"
            }`}
            onClick={onConfirm}
          >
            Confirmar
          </button>
        </div>
      </div>
    </div>
  );
}
