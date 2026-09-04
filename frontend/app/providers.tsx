"use client";

import { AuthProvider } from "@/context/AuthContext";
import { ThemeProvider } from "@/context/ThemeContext";
import NavShell from "@/components/NavShell";
import PushNotificationsSetup from "@/components/PushNotificationsSetup";
import BackButtonHandler from "@/components/BackButtonHandler";

export default function Providers({ children }: { children: React.ReactNode }) {
  return (
    <ThemeProvider>
      <AuthProvider>
        <PushNotificationsSetup />
        <BackButtonHandler />
        <NavShell>{children}</NavShell>
      </AuthProvider>
    </ThemeProvider>
  );
}
