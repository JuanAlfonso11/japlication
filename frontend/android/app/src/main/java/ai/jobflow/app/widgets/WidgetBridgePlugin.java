package ai.jobflow.app.widgets;

import com.getcapacitor.JSObject;
import com.getcapacitor.Plugin;
import com.getcapacitor.PluginCall;
import com.getcapacitor.PluginMethod;
import com.getcapacitor.annotation.CapacitorPlugin;

/**
 * El puente entre la app web y los widgets: `JobPilotWidgets` en
 * frontend/lib/widgets.ts.
 *
 * - update(data): la foto de lo que se ve, armada por la web.
 * - status(): si el widget ya tiene credencial, de qué cuenta, y el id de
 *   instalación con el que la web la pide.
 * - link(token, apiBase, userId): guarda la credencial del widget (solo
 *   abre /widget/* en el backend), para que ✕ / ✓ decidan sin abrir la app.
 * - clear(): cerrar sesión; revoca la credencial en el servidor y borra todo.
 *
 * Solo la puede llamar una página cargada en el WebView de la app, y ese
 * WebView solo navega a nuestro propio host (allowNavigation). Aun así, la
 * URL de la API se valida: la credencial nunca sale hacia otro servidor.
 */
@CapacitorPlugin(name = "JobPilotWidgets")
public class WidgetBridgePlugin extends Plugin {

    /** Una foto real ronda los 2 KB; esto deja margen de sobra y corta
     * cualquier cosa que no tenga pinta de serlo. */
    private static final int MAX_PAYLOAD_CHARS = 32_000;
    private static final int MAX_TOKEN_CHARS = 200;

    @PluginMethod
    public void update(PluginCall call) {
        String data = call.getString("data");
        if (data == null || data.length() > MAX_PAYLOAD_CHARS || WidgetData.parse(data) == null) {
            call.reject("Datos de widget no válidos.");
            return;
        }
        WidgetStore.save(getContext(), data);
        // La app acaba de enseñar la cola real: el aviso del último toque en
        // el widget ("Pasaste: X") ya no hace falta.
        WidgetStore.setNotice(getContext(), null);
        WidgetUpdater.updateAll(getContext());
        call.resolve();
    }

    @PluginMethod
    public void status(PluginCall call) {
        JSObject result = new JSObject();
        result.put("linked", WidgetStore.isLinked(getContext()));
        result.put("userId", WidgetStore.userId(getContext()));
        result.put("deviceId", WidgetStore.deviceId(getContext()));
        call.resolve(result);
    }

    @PluginMethod
    public void link(PluginCall call) {
        String token = call.getString("token");
        String apiBase = call.getString("apiBase");
        String userId = call.getString("userId");
        if (token == null || token.isEmpty() || token.length() > MAX_TOKEN_CHARS
                || !WidgetApi.isTrustedApiBase(apiBase) || !WidgetData.isSafeId(userId)) {
            call.reject("Credencial de widget no válida.");
            return;
        }
        WidgetStore.link(getContext(), token, apiBase, userId);
        // Los botones pasan de "abrir la app" a decidir en segundo plano, y
        // se trae la cola real ya con la credencial nueva.
        WidgetUpdater.updateAll(getContext());
        WidgetActions.refresh(getContext());
        call.resolve();
    }

    @PluginMethod
    public void clear(PluginCall call) {
        String token = WidgetStore.token(getContext());
        String apiBase = WidgetStore.apiBase(getContext());
        // Los toques que quedaran pendientes eran de esta sesión: fuera.
        WidgetWorker.cancelPending(getContext());
        WidgetStore.clear(getContext());
        WidgetUpdater.updateAll(getContext());
        WidgetActions.revoke(getContext(), token, apiBase);
        call.resolve();
    }
}
