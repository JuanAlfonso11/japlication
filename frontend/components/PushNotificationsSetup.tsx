"use client";

import { useEffect, useRef } from "react";
import { Capacitor, type PluginListenerHandle } from "@capacitor/core";
import { PushNotifications } from "@capacitor/push-notifications";
import { useAuth } from "@/context/AuthContext";
import { notificationsApi } from "@/lib/api";

/** Registers this device for push notifications once logged in — only does
 * anything inside the native Android app (Capacitor.isNativePlatform());
 * a no-op in a regular browser tab, since web push isn't wired up. Renders
 * nothing, just runs the registration side effect. */
export default function PushNotificationsSetup() {
  const { token } = useAuth();
  const attempted = useRef(false);

  useEffect(() => {
    if (!token || !Capacitor.isNativePlatform() || attempted.current) return;
    attempted.current = true;

    let registrationHandle: PluginListenerHandle | undefined;
    let errorHandle: PluginListenerHandle | undefined;

    async function setup() {
      registrationHandle = await PushNotifications.addListener("registration", (result) => {
        notificationsApi.registerDevice(result.value, "android").catch(() => {
          // Non-fatal — worst case this device just doesn't get pushes.
        });
      });
      errorHandle = await PushNotifications.addListener("registrationError", () => {
        // Non-fatal — same as above.
      });

      let permStatus = await PushNotifications.checkPermissions();
      if (permStatus.receive === "prompt") {
        permStatus = await PushNotifications.requestPermissions();
      }
      if (permStatus.receive !== "granted") return;

      await PushNotifications.register();
    }

    setup().catch(() => {
      // Non-fatal — push notifications are a nice-to-have, never block the app.
    });

    return () => {
      registrationHandle?.remove();
      errorHandle?.remove();
    };
  }, [token]);

  return null;
}
