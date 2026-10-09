package ai.jobflow.app.widgets;

import ai.jobflow.app.R;
import android.content.Context;
import android.util.Log;
import androidx.work.Data;
import java.io.IOException;
import org.json.JSONException;
import org.json.JSONObject;

/**
 * Lo que hacen ✕, ✓ y Deshacer del widget sin abrir la app.
 *
 * El orden importa para que se sienta inmediato:
 * 1. Se avanza la tarjeta en el widget YA, con la reserva que trae la foto
 *    (WidgetStore.advance), y se enseña "Pasaste: X" / "Guardada: X".
 * 2. Se encola en WorkManager (WidgetWorker) el mismo swipe que hace Home
 *    (POST /widget/decision → swipe_decision en el backend). WorkManager lo
 *    manda cuando hay red y lo reintenta si falla.
 * 3. La respuesta trae la cola real y la sustituye. Si al final no se pudo,
 *    la tarjeta vuelve a su sitio y el widget dice por qué.
 */
final class WidgetActions {

    private static final String TAG = "JobPilotWidget";

    static final String ACTION_DECIDE = "ai.jobflow.app.widgets.DECIDE";
    static final String ACTION_UNDO = "ai.jobflow.app.widgets.UNDO";
    static final String EXTRA_JOB_ID = "job_id";
    static final String EXTRA_DECISION = "decision";
    static final String EXTRA_TITLE = "title";
    static final String EXTRA_APPLICATION_ID = "application_id";

    private WidgetActions() {}

    // ------------------------------------------------- en el receiver (UI)

    static void decide(Context context, String jobId, String decision, String title) {
        Context app = context.getApplicationContext();
        boolean left = "left".equals(decision);
        if (!WidgetData.isSafeId(jobId) || !(left || "right".equals(decision))) return;
        if (!WidgetStore.isLinked(app)) {
            WidgetStore.setNotice(app, WidgetNotice.now(WidgetNotice.ERROR, app.getString(R.string.widget_error_relink), null));
            WidgetUpdater.updateAll(app);
            return;
        }

        String before = WidgetStore.rawPayload(app);
        String advanced = WidgetStore.advance(before, jobId);
        int seq = WidgetStore.nextSeq(app);
        if (before != null) WidgetStore.saveRollback(app, seq, before);
        if (advanced != null) WidgetStore.save(app, advanced);
        WidgetStore.setNotice(app, WidgetNotice.now(left ? WidgetNotice.PASSED : WidgetNotice.SAVED, title, null));
        WidgetUpdater.updateAll(app);

        WidgetWorker.enqueueAction(app, new Data.Builder()
            .putString(WidgetWorker.KEY_OP, WidgetWorker.OP_DECIDE)
            .putString(WidgetWorker.KEY_JOB_ID, jobId)
            .putString(WidgetWorker.KEY_DECISION, decision)
            .putString(WidgetWorker.KEY_TITLE, title)
            .putInt(WidgetWorker.KEY_SEQ, seq)
            .build());
    }

    static void undo(Context context, String applicationId, String title) {
        Context app = context.getApplicationContext();
        if (!WidgetData.isSafeId(applicationId) || !WidgetStore.isLinked(app)) return;
        // Mientras tanto se quita el "Deshacer", para que no se pulse dos veces.
        WidgetStore.setNotice(app, WidgetNotice.now(WidgetNotice.UNDONE, title, null));
        int seq = WidgetStore.nextSeq(app);
        WidgetUpdater.updateAll(app);

        WidgetWorker.enqueueAction(app, new Data.Builder()
            .putString(WidgetWorker.KEY_OP, WidgetWorker.OP_UNDO)
            .putString(WidgetWorker.KEY_APPLICATION_ID, applicationId)
            .putInt(WidgetWorker.KEY_SEQ, seq)
            .build());
    }

    /** Refresco en segundo plano (cada 30 min y al poner el widget), para que
     * la cola no se quede vieja aunque la app no se abra en días. */
    static void refresh(Context context) {
        Context app = context.getApplicationContext();
        if (WidgetStore.isLinked(app)) WidgetWorker.enqueueRefresh(app);
    }

    /** Cerrar sesión: revoca la credencial en el servidor. La sesión de la
     * app ya no existe, así que se usa la propia credencial. */
    static void revoke(Context context, String token, String apiBase) {
        if (token == null || apiBase == null) return;
        WidgetWorker.enqueueRevoke(context, token, apiBase);
    }

    // ------------------------------------------- en el WidgetWorker (red)
    // Devuelven true si hay que reintentar (error de red y quedan intentos).

    static boolean sendDecision(Context app, String jobId, String decision, String title,
                                int seq, boolean lastAttempt) {
        String token = WidgetStore.token(app);
        String apiBase = WidgetStore.apiBase(app);
        if (token == null || apiBase == null) {
            failed(app, 401, seq);
            return false;
        }
        try {
            JSONObject body = new JSONObject();
            body.put("job_id", jobId);
            body.put("decision", decision);
            WidgetApi.Response r = WidgetApi.call("POST", apiBase, "/widget/decision", token, body.toString());
            if (!r.ok()) {
                failed(app, r.status, seq);
                return false;
            }
            WidgetStore.takeRollback(app, seq);
            JSONObject res = new JSONObject(r.body);
            if (WidgetStore.currentSeq(app) == seq) {
                WidgetStore.save(app, res.getJSONObject("summary").toString());
                if ("left".equals(decision)) {
                    WidgetStore.setNotice(app, WidgetNotice.now(
                        WidgetNotice.PASSED, title, res.optString("application_id", null)));
                }
            }
            return false;
        } catch (IOException e) {
            Log.w(TAG, "decision: " + e.getClass().getSimpleName() + ": " + e.getMessage());
            if (!lastAttempt) return true;
            failed(app, 0, seq);
            return false;
        } catch (JSONException e) {
            // El swipe sí se guardó; solo falló leer la respuesta.
            WidgetStore.takeRollback(app, seq);
            fetchSummary(app, seq);
            return false;
        }
    }

    static boolean sendUndo(Context app, String applicationId, int seq, boolean lastAttempt) {
        String token = WidgetStore.token(app);
        String apiBase = WidgetStore.apiBase(app);
        if (token == null || apiBase == null) {
            failed(app, 401, seq);
            return false;
        }
        try {
            JSONObject body = new JSONObject();
            body.put("application_id", applicationId);
            WidgetApi.Response r = WidgetApi.call("POST", apiBase, "/widget/undo", token, body.toString());
            if (!r.ok()) {
                failed(app, r.status, seq);
            } else if (WidgetStore.currentSeq(app) == seq) {
                WidgetStore.save(app, new JSONObject(r.body).getJSONObject("summary").toString());
            }
            return false;
        } catch (IOException e) {
            Log.w(TAG, "undo: " + e.getClass().getSimpleName() + ": " + e.getMessage());
            if (!lastAttempt) return true;
            failed(app, 0, seq);
            return false;
        } catch (JSONException e) {
            fetchSummary(app, seq);
            return false;
        }
    }

    /** true si el servidor contestó (aunque fuera 401: ya no sirve). */
    static boolean sendRevoke(String token, String apiBase) {
        try {
            WidgetApi.call("DELETE", apiBase, "/widget/token", token, null);
            return true;
        } catch (IOException e) {
            // Sin red tras los reintentos: se queda viva en el servidor hasta
            // que este teléfono pida otra (que revoca la anterior) o se cambie
            // la contraseña. En el teléfono ya no existe.
            return false;
        }
    }

    static void fetchSummary(Context app, int seq) {
        String token = WidgetStore.token(app);
        String apiBase = WidgetStore.apiBase(app);
        if (token == null || apiBase == null) return;
        try {
            WidgetApi.Response r = WidgetApi.call("GET", apiBase, "/widget/summary", token, null);
            if (r.ok() && WidgetStore.currentSeq(app) == seq) {
                WidgetStore.save(app, new JSONObject(r.body).toString());
            } else if (r.status == 401) {
                WidgetStore.unlink(app);
            }
        } catch (IOException | JSONException e) {
            // Se queda la última foto; el próximo refresco lo reintenta.
            Log.w(TAG, "summary: " + e.getClass().getSimpleName());
        }
    }

    private static void failed(Context app, int status, int seq) {
        String before = WidgetStore.takeRollback(app, seq);
        String message;
        if (status == 401) {
            // Credencial revocada (otra sesión, contraseña nueva): ✕ / ✓
            // vuelven a abrir la app hasta que esta la reconecte.
            WidgetStore.unlink(app);
            message = app.getString(R.string.widget_error_relink);
        } else if (status == 404 || status == 400) {
            // Ya no estaba (decidida en la app, cerrada): se trae la cola real.
            fetchSummary(app, seq);
            WidgetStore.setNotice(app, WidgetNotice.now(
                WidgetNotice.ERROR, app.getString(R.string.widget_error_gone), null));
            return;
        } else {
            message = app.getString(status == 0 ? R.string.widget_error_offline : R.string.widget_error_generic);
        }
        if (before != null && WidgetStore.currentSeq(app) == seq) {
            WidgetStore.save(app, before); // la tarjeta vuelve a su sitio
        }
        WidgetStore.setNotice(app, WidgetNotice.now(WidgetNotice.ERROR, message, null));
    }
}
