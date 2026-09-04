"use client";

import { AuthProvider } from "@/context/AuthContext";
import { ThemeProvider } from "@/context/ThemeContext";
import NavShell from "@/components/NavShell";
import PushNotificationsSetup from "@/components/PushNotificationsSetup";

export default function Providers({ children }: { children: React.ReactNode }) {
  return (
    <ThemeProvider>
      <AuthProvider>
        <PushNotificationsSetup />
        <NavShell>{children}</NavShell>
      </AuthProvider>
    </ThemeProvider>
  );
}
