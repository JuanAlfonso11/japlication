package ai.jobflow.app;

import android.app.DownloadManager;
import android.content.Context;
import android.content.Intent;
import android.net.Uri;
import android.os.Bundle;
import android.os.Environment;
import android.webkit.URLUtil;
import android.widget.Toast;
import com.getcapacitor.BridgeActivity;

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
    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        handleViewIntent(getIntent());
        setupDownloadListener();
    }

    @Override
    public void onNewIntent(Intent intent) {
        super.onNewIntent(intent);
        handleViewIntent(intent);
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
                        downloadManager.enqueue(request);
                        Toast.makeText(getApplicationContext(), "Descargando actualización…", Toast.LENGTH_LONG).show();
                    }
                } catch (Exception e) {
                    Toast.makeText(getApplicationContext(), "No se pudo iniciar la descarga.", Toast.LENGTH_LONG).show();
                }
            });
    }
}
