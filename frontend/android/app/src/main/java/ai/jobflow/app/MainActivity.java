package ai.jobflow.app;

import android.content.Intent;
import android.net.Uri;
import android.os.Bundle;
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
}
