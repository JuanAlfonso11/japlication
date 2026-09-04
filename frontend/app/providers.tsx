"use client";

import { AuthProvider } from "@/context/AuthContext";
import { ThemeProvider } from "@/context/ThemeContext";
import NavShell from "@/components/NavShell";
import PushNotificationsSetup from "@/components/PushNotificationsSetup";
import BackButtonHandler from "@/components/BackButtonHandler";
import UpdateChecker from "@/components/UpdateChecker";

export default function Providers({ children }: { children: React.ReactNode }) {
  return (
    <ThemeProvider>
      <AuthProvider>
        <PushNotificationsSetup />
        <BackButtonHandler />
        <UpdateChecker />
        <NavShell>{children}</NavShell>
      </AuthProvider>
    </ThemeProvider>
  );
}
