import { Authenticated, Unauthenticated, useQuery } from "convex/react";
import { api } from "../convex/_generated/api";
import { SignInForm } from "./SignInForm";
import { SignOutButton } from "./SignOutButton";
import { Toaster } from "sonner";
import { JobBoard } from "./JobBoard";
import { PublicJobPreview } from "./PublicJobPreview";
import { AdminPage } from "./AdminPage";
import { useState } from "react";

export default function App() {
  const [showAdmin, setShowAdmin] = useState(false);

  return (
    <div className="min-h-screen flex flex-col bg-gray-50">
      <header className="sticky top-0 z-10 bg-white/80 backdrop-blur-sm h-16 flex justify-between items-center border-b shadow-sm px-4">
        <div className="flex items-center gap-4">
          <h2 className="text-xl font-semibold text-primary">JobBoard</h2>
          <button
            onClick={() => setShowAdmin(!showAdmin)}
            className="text-sm text-gray-600 hover:text-gray-900 underline"
          >
            {showAdmin ? "Back to Jobs" : "Admin"}
          </button>
        </div>
        <Authenticated>
          <SignOutButton />
        </Authenticated>
      </header>
      <main className="flex-1">
        {showAdmin ? <AdminPage /> : <Content />}
      </main>
      <Toaster />
    </div>
  );
}

function Content() {
  const loggedInUser = useQuery(api.auth.loggedInUser);

  if (loggedInUser === undefined) {
    return (
      <div className="flex justify-center items-center min-h-[400px]">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary"></div>
      </div>
    );
  }

  return (
    <div className="flex flex-col">
      <Authenticated>
        <JobBoard />
      </Authenticated>
      <Unauthenticated>
        <PublicJobPreview />
      </Unauthenticated>
    </div>
  );
}
