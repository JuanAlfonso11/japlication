package ai.jobflow.app.widgets;

import android.content.Context;
import android.content.SharedPreferences;
import java.util.UUID;
import org.json.JSONArray;
import org.json.JSONException;
import org.json.JSONObject;

/**
 * Todo lo que el widget guarda en el teléfono, en SharedPreferences privadas
 * de la app (ningún otro proceso las lee):
 *
 * - la "foto" que se ve (payload), venga de la app o del servidor;
 * - la credencial del widget (solo abre /widget/* en el backend, nunca la
 *   sesión de la app), la URL de la API y de qué cuenta es;
 * - un id de instalación, para que el servidor revoque la credencial vieja
 *   de este teléfono al emitir una nueva;
 * - el último aviso ("Pasaste: X · Deshacer", "Sin conexión"...).
 *
 * Se escribe con commit(): el widget lee desde otro hilo justo después.
 */
final class WidgetStore {

    private static final String PREFS = "jobpilot_widgets";
    private static final String KEY_PAYLOAD = "payload";
    private static final String KEY_TOKEN = "token";
    private static final String KEY_API_BASE = "api_base";
    private static final String KEY_USER_ID = "user_id";
    private static final String KEY_DEVICE_ID = "device_id";
    private static final String KEY_SEQ = "seq";
    private static final String KEY_NOTICE = "notice";

    /** Cuánto se queda visible un aviso. Después el widget vuelve a decir
     * "JobPilot" y "N en cola". */
    static final long NOTICE_TTL_MS = 10 * 60 * 1000L;

    private WidgetStore() {}

    private static SharedPreferences prefs(Context context) {
        return context.getApplicationContext().getSharedPreferences(PREFS, Context.MODE_PRIVATE);
    }

    // ----------------------------------------------------------- payload

    static void save(Context context, String json) {
        prefs(context).edit().putString(KEY_PAYLOAD, json).commit();
    }

    static String rawPayload(Context context) {
        return prefs(context).getString(KEY_PAYLOAD, null);
    }

    /** null si la app nunca mandó nada, o si se cerró sesión. */
    static WidgetData load(Context context) {
        return WidgetData.parse(rawPayload(context));
    }

    /**
     * La foto tras pasar o guardar `jobId`: la siguiente de la reserva pasa a
     * ser la de arriba y la cola baja en uno. Es lo que se ve al instante,
     * antes de que conteste el servidor. null si `jobId` ya no es la de
     * arriba (otro toque llegó antes).
     */
    static String advance(String json, String jobId) {
        if (json == null || jobId == null) return null;
        try {
            JSONObject root = new JSONObject(json);
            JSONObject next = root.optJSONObject("next");
            if (next == null || !jobId.equals(next.optString("id"))) return null;
            JSONArray upcoming = root.optJSONArray("upcoming");
            if (upcoming != null && upcoming.length() > 0) {
                root.put("next", upcoming.getJSONObject(0));
                upcoming.remove(0);
            } else {
                root.put("next", JSONObject.NULL);
            }
            root.put("queueCount", Math.max(0, root.optInt("queueCount", 0) - 1));
            return root.toString();
        } catch (JSONException e) {
            return null;
        }
    }

    // ----------------------------------------------------------- credencial

    static String token(Context context) {
        return prefs(context).getString(KEY_TOKEN, null);
    }

    static String apiBase(Context context) {
        return prefs(context).getString(KEY_API_BASE, null);
    }

    static String userId(Context context) {
        return prefs(context).getString(KEY_USER_ID, null);
    }

    static boolean isLinked(Context context) {
        return token(context) != null && apiBase(context) != null;
    }

    static void link(Context context, String token, String apiBase, String userId) {
        prefs(context).edit()
            .putString(KEY_TOKEN, token)
            .putString(KEY_API_BASE, apiBase)
            .putString(KEY_USER_ID, userId)
            .commit();
    }

    /** Quita la credencial pero deja la foto: el widget sigue enseñando la
     * última cola y ✕ / ✓ vuelven a abrir la app hasta que se reconecte. */
    static void unlink(Context context) {
        prefs(context).edit().remove(KEY_TOKEN).remove(KEY_USER_ID).commit();
    }

    /** Cerrar sesión: fuera todo menos el id de instalación. */
    static void clear(Context context) {
        prefs(context).edit()
            .remove(KEY_PAYLOAD)
            .remove(KEY_TOKEN)
            .remove(KEY_API_BASE)
            .remove(KEY_USER_ID)
            .remove(KEY_NOTICE)
            .commit();
    }

    static synchronized String deviceId(Context context) {
        SharedPreferences p = prefs(context);
        String id = p.getString(KEY_DEVICE_ID, null);
        if (id == null) {
            id = UUID.randomUUID().toString();
            p.edit().putString(KEY_DEVICE_ID, id).commit();
        }
        return id;
    }

    // ----------------------------------------------------------- orden

    /** Cada toque recibe un número. Una respuesta solo pisa la foto si sigue
     * siendo la del último toque: así un servidor lento no "devuelve" una
     * tarjeta que ya pasaste con el toque siguiente. */
    static synchronized int nextSeq(Context context) {
        int seq = prefs(context).getInt(KEY_SEQ, 0) + 1;
        prefs(context).edit().putInt(KEY_SEQ, seq).commit();
        return seq;
    }

    static int currentSeq(Context context) {
        return prefs(context).getInt(KEY_SEQ, 0);
    }

    // ----------------------------------------------------------- aviso

    static void setNotice(Context context, WidgetNotice notice) {
        SharedPreferences.Editor e = prefs(context).edit();
        if (notice == null) e.remove(KEY_NOTICE);
        else e.putString(KEY_NOTICE, notice.toJson());
        e.commit();
    }

    /** El aviso vigente, o null si no hay o ya caducó. */
    static WidgetNotice notice(Context context) {
        WidgetNotice n = WidgetNotice.parse(prefs(context).getString(KEY_NOTICE, null));
        if (n == null || System.currentTimeMillis() - n.at > NOTICE_TTL_MS) return null;
        return n;
    }
}
