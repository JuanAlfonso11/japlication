package ai.jobflow.app.widgets;

import ai.jobflow.app.MainActivity;
import android.app.PendingIntent;
import android.content.Context;
import android.content.Intent;
import android.net.Uri;

/**
 * Cada toque en un widget abre la app en una ruta de la propia web
 * (https://<host tailscale>/...). Va por el mismo camino que los enlaces de
 * los correos: un VIEW intent a MainActivity, que comprueba que el host sea
 * el nuestro (isTrustedAppUri) y lo carga en el WebView. Así no hace falta
 * ningún código nuevo de navegación en Java: la app web decide qué hacer
 * con `/?swipe=right&job=...`, `/applications?status=offer`, etc.
 */
final class WidgetLinks {

    /** El mismo host que capacitor.config.ts (server.url) y MainActivity. */
    static final String HOST = "jobpilot.tailb3d4c1.ts.net";

    private WidgetLinks() {}

    static PendingIntent open(Context context, String path, int requestCode) {
        Intent intent = new Intent(Intent.ACTION_VIEW, Uri.parse("https://" + HOST + path));
        intent.setClass(context, MainActivity.class);
        // singleTask en el manifest: si la app ya está abierta llega por
        // onNewIntent en vez de abrir una segunda copia.
        intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_SINGLE_TOP);
        return PendingIntent.getActivity(
            context,
            requestCode,
            intent,
            PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE
        );
    }

    /** Un código distinto por widget y por botón, para que Android no
     * confunda un PendingIntent con otro al actualizar. */
    static int requestCode(int appWidgetId, int action) {
        return appWidgetId * 16 + action;
    }
}
