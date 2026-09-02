"use client";

import { AuthProvider } from "@/context/AuthContext";
import NavShell from "@/components/NavShell";

export default function Providers({ children }: { children: React.ReactNode }) {
  return (
    <AuthProvider>
      <NavShell>{children}</NavShell>
    </AuthProvider>
  );
}
