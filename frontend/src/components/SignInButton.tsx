"use client";

import { LogIn, LogOut } from "lucide-react";
import { signIn, signOut, useSession } from "next-auth/react";

export default function SignInButton() {
  const { data: session, status } = useSession();

  if (status === "loading") {
    return (
      <button className="text-xs px-3 py-1.5 rounded-lg border border-slate-200 text-slate-500">
        Checking session...
      </button>
    );
  }

  if (session?.user) {
    return (
      <button
        onClick={() => signOut()}
        className="inline-flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg border border-slate-300 hover:border-slate-500 transition-colors"
      >
        <LogOut size={14} />
        Sign out
      </button>
    );
  }

  return (
    <button
      onClick={() => signIn("google")}
      className="inline-flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg bg-slate-900 text-white hover:bg-slate-700 transition-colors"
    >
      <LogIn size={14} />
      Sign in with Google
    </button>
  );
}
