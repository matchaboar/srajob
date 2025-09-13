import { Fragment } from "react";

interface Props {
  open: boolean;
  onClose: () => void;
  title?: string;
  data?: Record<string, any> | null;
  logs?: { fieldsYaml?: string; fillLogYaml?: string; screenshot?: string } | null;
}

export default function DataDrawer({ open, onClose, title, data, logs }: Props) {
  return (
    <div className={`fixed inset-0 z-50 ${open ? '' : 'pointer-events-none'}`}>
      {/* Backdrop */}
      <div
        className={`absolute inset-0 bg-black/30 transition-opacity ${open ? 'opacity-100' : 'opacity-0'}`}
        onClick={onClose}
      />
      {/* Panel */}
      <div
        className={`absolute top-0 right-0 h-full w-full sm:w-[480px] bg-white shadow-xl transform transition-transform ${
          open ? 'translate-x-0' : 'translate-x-full'
        }`}
      >
        <div className="flex items-center justify-between px-4 py-3 border-b">
          <div className="font-semibold text-gray-900">{title || 'Filled Data'}</div>
          <button
            onClick={onClose}
            className="rounded-md px-2 py-1 text-sm text-gray-600 hover:bg-gray-100"
            aria-label="Close"
          >
            Close
          </button>
        </div>
        <div className="p-4 space-y-4 overflow-y-auto h-[calc(100%-48px)]">
          {data && Object.keys(data).length > 0 ? (
            <div>
              <div className="text-sm font-medium text-gray-700 mb-2">Fields</div>
              <div className="text-sm divide-y border rounded-md">
                {Object.entries(data).map(([k, v]) => (
                  <div key={k} className="px-3 py-2 flex gap-3">
                    <div className="w-40 shrink-0 text-gray-600">{k}</div>
                    <div className="flex-1 break-words">
                      {typeof v === 'string' ? v : Array.isArray(v) ? v.join(', ') : JSON.stringify(v)}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          ) : (
            <div className="text-sm text-gray-500">No filled data available.</div>
          )}

          {(logs && (logs.fieldsYaml || logs.fillLogYaml || logs.screenshot)) && (
            <div>
              <div className="text-sm font-medium text-gray-700 mb-2">Logs</div>
              <div className="text-xs bg-gray-50 border rounded-md p-3 text-gray-700 space-y-2">
                {logs.fieldsYaml && (
                  <div>
                    <div className="font-semibold mb-1">fieldsYaml:</div>
                    <pre className="whitespace-pre-wrap break-words bg-white border rounded p-2 text-[11px] leading-4 overflow-auto max-h-64">
                      {logs.fieldsYaml}
                    </pre>
                  </div>
                )}
                {logs.fillLogYaml && (
                  <div className="mb-1"><span className="font-semibold">fillLogYaml:</span> {logs.fillLogYaml}</div>
                )}
                {logs.screenshot && (
                  <div>
                    <div className="font-semibold mb-1">screenshot:</div>
                    <img src={logs.screenshot} alt="Filled form screenshot" className="border rounded max-w-full" style={{ width: 200 }} />
                  </div>
                )}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
