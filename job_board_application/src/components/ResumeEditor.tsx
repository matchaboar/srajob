import { useState } from "react";
import { useMutation } from "convex/react";
import { api } from "../../convex/_generated/api";
import { toast } from "sonner";

export default function ResumeEditor() {
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const storeResume = useMutation(api.formFiller.storeResume);

  const save = async () => {
    if (!text.trim()) {
      toast.error("Paste your resume YAML first");
      return;
    }
    setBusy(true);
    try {
      // Store raw YAML text; server workflow will use it as-is
      await storeResume({ resume: text });
      toast.success("Resume saved");
    } catch (e: any) {
      toast.error(e?.message || "Failed to save resume");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex items-start gap-2">
      <textarea
        value={text}
        onChange={(e) => setText(e.target.value)}
        rows={5}
        placeholder="Paste your resume YAML here"
        className="w-80 text-xs p-2 border rounded-md font-mono"
      />
      <button
        onClick={save}
        disabled={busy}
        className="h-9 px-3 bg-blue-600 text-white rounded-md text-xs hover:bg-blue-700 disabled:opacity-50"
      >
        {busy ? "Saving…" : "Save Resume"}
      </button>
    </div>
  );
}

