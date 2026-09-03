"use client";

import { AuthProvider } from "@/context/AuthContext";
import { ThemeProvider } from "@/context/ThemeContext";
import NavShell from "@/components/NavShell";

export default function Providers({ children }: { children: React.ReactNode }) {
  return (
    <ThemeProvider>
      <AuthProvider>
        <NavShell>{children}</NavShell>
      </AuthProvider>
    </ThemeProvider>
  );
}
