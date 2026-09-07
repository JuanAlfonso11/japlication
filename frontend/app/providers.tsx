"use client";

import { useEffect } from "react";
import { AuthProvider } from "@/context/AuthContext";
import { ThemeProvider } from "@/context/ThemeContext";
import NavShell from "@/components/NavShell";
import PushNotificationsSetup from "@/components/PushNotificationsSetup";
import BackButtonHandler from "@/components/BackButtonHandler";
import UpdateChecker from "@/components/UpdateChecker";
import ErrorBoundary from "@/components/ErrorBoundary";
import { installErrorReporting } from "@/lib/errorReporting";

export default function Providers({ children }: { children: React.ReactNode }) {
  // Global handlers for anything that escapes React's own boundary: a throw
  // inside an event handler, a rejected promise nobody awaited. Installed
  // once, in an effect so it only ever runs in the browser.
  useEffect(() => {
    installErrorReporting();
  }, []);

  return (
    <ThemeProvider>
      <AuthProvider>
        <PushNotificationsSetup />
        <BackButtonHandler />
        <UpdateChecker />
        {/* Inside NavShell, not around it: a page crashing should leave the
            tab bar and header alive so the user can navigate away, rather
            than blanking the entire app. */}
        <NavShell>
          <ErrorBoundary>{children}</ErrorBoundary>
        </NavShell>
      </AuthProvider>
    </ThemeProvider>
  );
}
