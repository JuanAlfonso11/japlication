package ai.jobflow.app.widgets;

import com.getcapacitor.Plugin;
import com.getcapacitor.PluginCall;
import com.getcapacitor.PluginMethod;
import com.getcapacitor.annotation.CapacitorPlugin;

/**
 * El puente entre la app web y los widgets: `JobPilotWidgets` en
 * frontend/lib/widgets.ts.
 *
 * La web manda la foto ya armada como texto JSON; aquí solo se comprueba
 * que sea un JSON de widget razonable, se guarda y se redibujan los widgets.
 * Solo la puede llamar una página cargada en el WebView de la app, y ese
 * WebView solo navega a nuestro propio host (allowNavigation).
 */
@CapacitorPlugin(name = "JobPilotWidgets")
public class WidgetBridgePlugin extends Plugin {

    /** Una foto real ronda los 500 bytes; esto deja margen de sobra y corta
     * cualquier cosa que no tenga pinta de serlo. */
    private static final int MAX_PAYLOAD_CHARS = 16_000;

    @PluginMethod
    public void update(PluginCall call) {
        String data = call.getString("data");
        if (data == null || data.length() > MAX_PAYLOAD_CHARS || WidgetData.parse(data) == null) {
            call.reject("Datos de widget no válidos.");
            return;
        }
        WidgetStore.save(getContext(), data);
        WidgetUpdater.updateAll(getContext());
        call.resolve();
    }

    @PluginMethod
    public void clear(PluginCall call) {
        WidgetStore.clear(getContext());
        WidgetUpdater.updateAll(getContext());
        call.resolve();
    }
}
