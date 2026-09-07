package ai.jobflow.app;

import android.app.DownloadManager;
import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.content.IntentFilter;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.os.Environment;
import android.provider.Settings;
import android.webkit.URLUtil;
import android.widget.Toast;
import androidx.core.content.FileProvider;
import com.getcapacitor.BridgeActivity;
import java.io.File;
import java.io.UnsupportedEncodingException;
import java.net.URLEncoder;

/**
 * Capacitor's WebView always loads capacitor.config.ts's server.url on
 * launch by default — it does not, on its own, act on the URI a VIEW
 * intent (e.g. AndroidManifest.xml's tailscale-host intent-filter, matched
 * when the user taps the verification email's link) was launched with.
 * This forwards that URI straight into the WebView instead, so tapping the
 * link and having Android open JobPilot actually navigates to it (letting
 * the backend validate the token and redirect, same as a normal browser
 * tap would) rather than just opening the app to its default Home screen.
 *
 * (This class previously also excluded Android's edge swipe-back gesture
 * app-wide via setSystemGestureExclusionRects(), as a fix attempt for
 * Home's swipe cards not registering one-finger drags. That turned out to
 * be the wrong layer entirely — the real cause was a CSS touch-action
 * inheritance gap (see globals.css) — and excluding the whole window had
 * the side effect of also disabling the OS back-gesture everywhere else
 * in the app, e.g. backing out of a job's detail page. Removed.)
 */
public class MainActivity extends BridgeActivity {

    /** The in-flight update download, so the completion receiver below only
     * acts on our own APK and ignores every other download on the device. */
    private long updateDownloadId = -1L;
    private BroadcastReceiver downloadCompleteReceiver;

    /** Set when a share arrives before the WebView is ready to navigate, so
     * onCreate's share isn't dropped on the floor while Capacitor is still
     * loading the app. */
    private String pendingSharedText;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        handleViewIntent(getIntent());
        handleShareIntent(getIntent());
        setupDownloadListener();
        registerDownloadCompleteReceiver();
    }

    // public, not protected: BridgeActivity declares onDestroy() public and
    // Java forbids narrowing an override's visibility.
    @Override
    public void onDestroy() {
        if (downloadCompleteReceiver != null) {
            try {
                unregisterReceiver(downloadCompleteReceiver);
            } catch (IllegalArgumentException ignored) {
                // Already unregistered — nothing to undo.
            }
            downloadCompleteReceiver = null;
        }
        super.onDestroy();
    }

    @Override
    public void onNewIntent(Intent intent) {
        super.onNewIntent(intent);
        handleViewIntent(intent);
        handleShareIntent(intent);
    }

    @Override
    public void onResume() {
        super.onResume();
        // A share that arrived during onCreate (cold start) can't navigate
        // yet — the bridge/WebView isn't up. By the time we're resumed it
        // is, so replay it here. launchMode is singleTask, so a share into
        // an already-running app goes through onNewIntent instead and is
        // handled immediately.
        if (pendingSharedText != null) {
            String text = pendingSharedText;
            pendingSharedText = null;
            navigateToImport(text);
        }
    }

    private void handleViewIntent(Intent intent) {
        if (intent == null || !Intent.ACTION_VIEW.equals(intent.getAction())) return;
        Uri data = intent.getData();
        if (data == null) return;
        if (getBridge() != null && getBridge().getWebView() != null) {
            getBridge().getWebView().loadUrl(data.toString());
        }
    }

    /**
     * Receives a posting shared from any other app (Chrome, LinkedIn,
     * WhatsApp) and hands it to the import screen.
     *
     * The text is passed through as-is rather than parsed here: apps send
     * wildly different shapes (a bare URL, "Mira esta vacante: <url>", a
     * title and a URL on separate lines), and the web side already has the
     * extractor for that — with tests — so keeping one implementation in
     * JavaScript beats a second, subtly different one in Java.
     */
    private void handleShareIntent(Intent intent) {
        if (intent == null || !Intent.ACTION_SEND.equals(intent.getAction())) return;

        String shared = intent.getStringExtra(Intent.EXTRA_TEXT);
        if (shared == null || shared.trim().isEmpty()) {
            // Some apps put the link in the subject instead of the body.
            shared = intent.getStringExtra(Intent.EXTRA_SUBJECT);
        }
        if (shared == null || shared.trim().isEmpty()) return;

        // Consume it, so a configuration change (rotation) doesn't replay
        // the same share and import the job twice.
        intent.removeExtra(Intent.EXTRA_TEXT);
        intent.removeExtra(Intent.EXTRA_SUBJECT);

        if (!navigateToImport(shared)) {
            pendingSharedText = shared;
        }
    }

    /** Returns false when the WebView isn't ready yet, so the caller can
     * hold the share until onResume. */
    private boolean navigateToImport(String sharedText) {
        if (getBridge() == null || getBridge().getWebView() == null) return false;
        try {
            String base = getBridge().getServerUrl();
            if (base == null || base.isEmpty()) {
                base = getBridge().getLocalUrl();
            }
            if (base == null || base.isEmpty()) return false;

            String target = base.replaceAll("/+$", "")
                + "/jobs/import?shared="
                + URLEncoder.encode(sharedText, "UTF-8");
            getBridge().getWebView().loadUrl(target);
            return true;
        } catch (UnsupportedEncodingException e) {
            // UTF-8 is always available; this branch exists only because the
            // checked exception has to go somewhere.
            return false;
        }
    }

    /**
     * The update banner (UpdateChecker.tsx) links straight to the APK
     * download — but that URL shares JobPilot's own Tailscale hostname
     * (already in capacitor.config.ts's allowNavigation, needed for the
     * email-verification link), so Capacitor's own external-link handling
     * (Bridge.launchIntent, host-based) treats it as an in-app navigation
     * rather than something to hand off externally. A bare WebView also
     * has no DownloadListener by default — Capacitor doesn't register one
     * — so without this, tapping the link would just try to "render" the
     * APK's bytes as a page and silently fail. Registering one hands any
     * non-renderable response (the APK's Content-Disposition: attachment)
     * to Android's own DownloadManager, the same system-level download +
     * "tap notification to install" flow a normal browser gives you.
     */
    private void setupDownloadListener() {
        if (getBridge() == null || getBridge().getWebView() == null) return;
        getBridge()
            .getWebView()
            .setDownloadListener((url, userAgent, contentDisposition, mimetype, contentLength) -> {
                try {
                    String filename = URLUtil.guessFileName(url, contentDisposition, mimetype);
                    DownloadManager.Request request = new DownloadManager.Request(Uri.parse(url));
                    request.setMimeType(mimetype);
                    request.setNotificationVisibility(DownloadManager.Request.VISIBILITY_VISIBLE_NOTIFY_COMPLETED);
                    request.setDestinationInExternalPublicDir(Environment.DIRECTORY_DOWNLOADS, filename);
                    DownloadManager downloadManager = (DownloadManager) getSystemService(Context.DOWNLOAD_SERVICE);
                    if (downloadManager != null) {
                        updateDownloadId = downloadManager.enqueue(request);
                        Toast.makeText(getApplicationContext(), "Descargando actualización…", Toast.LENGTH_LONG).show();
                    }
                } catch (Exception e) {
                    Toast.makeText(getApplicationContext(), "No se pudo iniciar la descarga.", Toast.LENGTH_LONG).show();
                }
            });
    }

    /**
     * Turns "downloaded" into "installing" without the user leaving the app.
     *
     * DownloadManager only ever *fetches* the file — it drops a notification
     * and stops there. That left the update flow as: tap Descargar, wait,
     * pull down the shade (or open Files), find jobpilot.apk, tap it,
     * confirm. Every other app just asks for confirmation and installs, and
     * the difference is only this: firing ACTION_INSTALL_PACKAGE (via the
     * generic VIEW intent, which is what still works across versions) as
     * soon as the download our own listener started reports completion.
     *
     * Android keeps the user in control either way — the install screen
     * always asks, and the first time it also makes them grant JobPilot
     * "install unknown apps" in Settings. Nothing installs silently; the
     * manual hunt for the file is what goes away.
     */
    private void registerDownloadCompleteReceiver() {
        downloadCompleteReceiver = new BroadcastReceiver() {
            @Override
            public void onReceive(Context context, Intent intent) {
                long completedId = intent.getLongExtra(DownloadManager.EXTRA_DOWNLOAD_ID, -1L);
                // -1 guards the case where this fires for somebody else's
                // download before we ever started one of our own.
                if (updateDownloadId == -1L || completedId != updateDownloadId) return;
                promptInstall(completedId);
            }
        };

        IntentFilter filter = new IntentFilter(DownloadManager.ACTION_DOWNLOAD_COMPLETE);
        // Android 13+ requires every runtime-registered receiver to declare
        // whether it accepts broadcasts from other apps. DownloadManager's
        // completion broadcast comes from the system, so exported is the
        // correct (and required) choice here — NOT_EXPORTED would silently
        // never fire.
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            registerReceiver(downloadCompleteReceiver, filter, Context.RECEIVER_EXPORTED);
        } else {
            registerReceiver(downloadCompleteReceiver, filter);
        }
    }

    private void promptInstall(long downloadId) {
        DownloadManager downloadManager = (DownloadManager) getSystemService(Context.DOWNLOAD_SERVICE);
        if (downloadManager == null) return;

        Uri apkUri = downloadManager.getUriForDownloadedFile(downloadId);
        if (apkUri == null) {
            Toast.makeText(getApplicationContext(), "La descarga no se completó.", Toast.LENGTH_LONG).show();
            return;
        }

        // getUriForDownloadedFile() usually hands back a content:// URI the
        // installer can read directly, but for downloads written to a public
        // directory some Android builds return a plain file:// path instead.
        // Putting a file:// URI in an Intent has thrown FileUriExposedException
        // since Android 7, so the install would die instead of prompting.
        // Re-wrapping it through our own FileProvider (already declared in the
        // manifest; file_paths.xml maps the whole external root, which covers
        // Downloads) makes both shapes end up as a grantable content:// URI.
        if ("file".equals(apkUri.getScheme()) && apkUri.getPath() != null) {
            try {
                apkUri = FileProvider.getUriForFile(
                    this,
                    getPackageName() + ".fileprovider",
                    new File(apkUri.getPath())
                );
            } catch (IllegalArgumentException e) {
                Toast.makeText(
                    getApplicationContext(),
                    "Descarga lista. Ábrela desde tus notificaciones para instalar.",
                    Toast.LENGTH_LONG
                ).show();
                return;
            }
        }

        // On O+ the install intent is refused outright unless the user has
        // allowed this app as an install source. Sending them straight to
        // that toggle is far clearer than letting the installer bounce with
        // a bare "for your security" message and no obvious next step.
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O
                && !getPackageManager().canRequestPackageInstalls()) {
            Toast.makeText(
                getApplicationContext(),
                "Permite instalar apps desde JobPilot para completar la actualización.",
                Toast.LENGTH_LONG
            ).show();
            try {
                startActivity(
                    new Intent(Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES)
                        .setData(Uri.parse("package:" + getPackageName()))
                );
                // The install itself is retried by the user tapping the
                // download notification, which now has the permission it
                // needs. Re-firing it automatically here would race the
                // Settings screen the user is still looking at.
                return;
            } catch (Exception e) {
                // Some OEM builds don't expose that Settings screen; fall
                // through and let the installer show whatever it shows.
            }
        }

        try {
            Intent install = new Intent(Intent.ACTION_VIEW);
            install.setDataAndType(apkUri, "application/vnd.android.package-archive");
            install.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION);
            install.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
            startActivity(install);
        } catch (Exception e) {
            Toast.makeText(
                getApplicationContext(),
                "Descarga lista. Ábrela desde tus notificaciones para instalar.",
                Toast.LENGTH_LONG
            ).show();
        }
    }
}
