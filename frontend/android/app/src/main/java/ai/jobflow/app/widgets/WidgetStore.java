package ai.jobflow.app.widgets;

import android.content.Context;
import android.content.SharedPreferences;

/** Dónde vive la foto entre que la app la manda y el widget la dibuja.
 * SharedPreferences privadas de la app: ningún otro proceso la lee, y no
 * contiene nada de la sesión (ni token ni correo), solo lo que se ve. */
final class WidgetStore {

    private static final String PREFS = "jobpilot_widgets";
    private static final String KEY_PAYLOAD = "payload";

    private WidgetStore() {}

    private static SharedPreferences prefs(Context context) {
        return context.getApplicationContext().getSharedPreferences(PREFS, Context.MODE_PRIVATE);
    }

    static void save(Context context, String json) {
        prefs(context).edit().putString(KEY_PAYLOAD, json).apply();
    }

    static void clear(Context context) {
        prefs(context).edit().remove(KEY_PAYLOAD).apply();
    }

    /** null si la app nunca mandó nada, o si se cerró sesión. */
    static WidgetData load(Context context) {
        return WidgetData.parse(prefs(context).getString(KEY_PAYLOAD, null));
    }
}
