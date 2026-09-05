"use client";

import { useEffect, useState } from "react";
import { Capacitor } from "@capacitor/core";
import { App } from "@capacitor/app";
import { appUpdateApi } from "@/lib/api";
import type { AndroidUpdateInfo } from "@/lib/types";

// Re-checks periodically while the app stays open (not just at launch) —
// a session left open for hours would otherwise never notice a build
// shipped in the meantime until the next cold start.
const RECHECK_INTERVAL_MS = 30 * 60 * 1000;

/** Checks whether a newer native build than the one installed is
 * available (at launch, then every 30 minutes while the app stays open),
 * and shows a dismissible banner with a direct download link if so — the
 * whole point being no cable needed. Only does anything inside the
 * native Android app (a no-op in a regular browser tab, same guard as
 * BackButtonHandler), and only ever needs the backend reachable, not any
 * prior login.
 *
 * The APK still can't install itself — Android requires an explicit tap
 * on the "Install" screen no app can skip — but everything up to that
 * point (checking, prompting, downloading) runs on its own. Tapping
 * "Descargar" hands the URL to the WebView's DownloadListener (see
 * MainActivity.java), which hands it to Android's own DownloadManager —
 * the same "downloading… tap notification to install" flow a normal
 * browser download gives you. */
export default function UpdateChecker() {
  const [update, setUpdate] = useState<AndroidUpdateInfo | null>(null);
  const [dismissed, setDismissed] = useState(false);

  useEffect(() => {
    if (!Capacitor.isNativePlatform()) return;

    let cancelled = false;

    async function checkForUpdate() {
      try {
        const [info, current] = await Promise.all([appUpdateApi.check(), App.getInfo()]);
        if (cancelled) return;
        const latestCode = info.version_code;
        const currentCode = parseInt(current.build, 10);
        if (latestCode != null && info.apk_url && !Number.isNaN(currentCode) && latestCode > currentCode) {
          setUpdate(info);
        }
      } catch {
        // Never block app usage over a failed/unreachable update check.
      }
    }

    checkForUpdate();
    const interval = setInterval(checkForUpdate, RECHECK_INTERVAL_MS);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, []);

  if (!update || dismissed || !update.apk_url) return null;

  return (
    <div className="fixed inset-x-0 bottom-16 z-50 mx-auto w-[calc(100%-1.5rem)] max-w-md rounded-2xl bg-brand-600 p-4 text-white shadow-lg md:bottom-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-sm font-semibold">
            Hay una actualización de JobPilot{update.version_name ? ` (v${update.version_name})` : ""}
          </p>
          {update.notes && <p className="mt-1 text-xs text-brand-100">{update.notes}</p>}
        </div>
        <button
          type="button"
          onClick={() => setDismissed(true)}
          aria-label="Cerrar"
          className="shrink-0 text-brand-200 hover:text-white"
        >
          ✕
        </button>
      </div>
      <a
        href={update.apk_url}
        className="mt-3 inline-block rounded-lg bg-white px-4 py-2 text-sm font-semibold text-brand-700 hover:bg-brand-50"
      >
        Descargar actualización
      </a>
    </div>
  );
}
