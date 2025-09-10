import { createRoot } from "react-dom/client";
import { ConvexAuthProvider } from "@convex-dev/auth/react";
import { ConvexReactClient } from "convex/react";
import "./index.css";
import App from "./App";

const rootEl = document.getElementById("root")!;
const url = import.meta.env.VITE_CONVEX_URL as string | undefined;
const isPlaceholder = !url || url.includes("<your-deployment>");

if (isPlaceholder) {
  const Note = () => (
    <div style={{ padding: 24, fontFamily: "ui-sans-serif,system-ui" }}>
      <h1 style={{ fontSize: 20, fontWeight: 600, marginBottom: 12 }}>Setup Required</h1>
      <p style={{ color: "#374151", lineHeight: 1.6 }}>
        VITE_CONVEX_URL is not configured. Update <code>.env.local</code> with a
        valid Convex URL or run <code>npx convex dev</code> and copy the URL it
        prints. When configured, the Job Board UI will load.
      </p>
      <p style={{ marginTop: 12, color: "#6B7280" }}>
        Current value: <code>{String(url || "(missing)")}</code>
      </p>
    </div>
  );
  createRoot(rootEl).render(<Note />);
} else {
  const convex = new ConvexReactClient(url, {
    // In dev we may use different hostnames; skip strict URL checks
    skipConvexDeploymentUrlCheck: true,
    verbose: true,
  });
  createRoot(rootEl).render(
    <ConvexAuthProvider client={convex}>
      <App />
    </ConvexAuthProvider>,
  );
}
