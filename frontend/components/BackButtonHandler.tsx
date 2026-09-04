"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { Capacitor } from "@capacitor/core";
import { App } from "@capacitor/app";

/** Wires Android's hardware/gesture back button into the app's own
 * navigation history. Capacitor doesn't do this on its own — with no
 * listener registered, pressing back (or swiping back from the edge)
 * exits the app straight from wherever you are, instead of stepping back
 * through it (e.g. backing out of a job's detail page kicked you out of
 * JobPilot entirely instead of returning to the swipe queue). `canGoBack`
 * reflects the WebView's own history, which Next.js's client-side
 * navigation already feeds via the History API. Only does anything inside
 * the native Android app — a no-op in a regular browser tab. */
export default function BackButtonHandler() {
  const router = useRouter();

  useEffect(() => {
    if (!Capacitor.isNativePlatform()) return;

    const listenerPromise = App.addListener("backButton", ({ canGoBack }) => {
      if (canGoBack) {
        router.back();
      } else {
        // Nothing left to step back to (already at the root) — background
        // the app, same as pressing Home, rather than killing it outright.
        App.minimizeApp();
      }
    });

    return () => {
      listenerPromise.then((handle) => handle.remove());
    };
  }, [router]);

  return null;
}
