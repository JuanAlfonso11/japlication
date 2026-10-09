package ai.jobflow.app.widgets;

import ai.jobflow.app.R;
import android.content.BroadcastReceiver;
import android.content.Context;
import java.io.IOException;
import org.json.JSONException;
import org.json.JSONObject;

/**
 * Lo que hacen ✕, ✓ y Deshacer del widget sin abrir la app.
 *
 * El orden importa para que se sienta inmediato:
 * 1. Se avanza la tarjeta en el widget YA, con la reserva que trae la foto
 *    (WidgetStore.advance), y se enseña "Pasaste: X" / "Guardada: X".
 * 2. En segundo plano se manda el mismo swipe que hace Home
 *    (POST /widget/decision → swipe_decision en el backend).
 * 3. La respuesta trae la cola real y la sustituye. Si falla, la tarjeta
 *    vuelve a su sitio y el widget dice por qué.
 */
final class WidgetActions {

    static final String ACTION_DECIDE = "ai.jobflow.app.widgets.DECIDE";
    static final String ACTION_UNDO = "ai.jobflow.app.widgets.UNDO";
    static final String EXTRA_JOB_ID = "job_id";
    static final String EXTRA_DECISION = "decision";
    static final String EXTRA_TITLE = "title";
    static final String EXTRA_APPLICATION_ID = "application_id";

    private WidgetActions() {}

    static void decide(Context context, String jobId, String decision, String title,
                       BroadcastReceiver.PendingResult pending) {
        Context app = context.getApplicationContext();
        boolean left = "left".equals(decision);
        if (!WidgetData.isSafeId(jobId) || !(left || "right".equals(decision))) {
            finish(app, pending);
            return;
        }
        String token = WidgetStore.token(app);
        String apiBase = WidgetStore.apiBase(app);
        if (token == null || apiBase == null) {
            WidgetStore.setNotice(app, WidgetNotice.now(WidgetNotice.ERROR, app.getString(R.string.widget_error_relink), null));
            finish(app, pending);
            return;
        }

        String before = WidgetStore.rawPayload(app);
        String advanced = WidgetStore.advance(before, jobId);
        if (advanced != null) WidgetStore.save(app, advanced);
        WidgetStore.setNotice(app, WidgetNotice.now(left ? WidgetNotice.PASSED : WidgetNotice.SAVED, title, null));
        int seq = WidgetStore.nextSeq(app);
        WidgetUpdater.updateAll(app);

        WidgetApi.EXECUTOR.execute(() -> {
            try {
                JSONObject body = new JSONObject();
                body.put("job_id", jobId);
                body.put("decision", decision);
                WidgetApi.Response r = WidgetApi.call("POST", apiBase, "/widget/decision", token, body.toString());
                if (r.ok()) {
                    JSONObject res = new JSONObject(r.body);
                    if (WidgetStore.currentSeq(app) == seq) {
                        WidgetStore.save(app, res.getJSONObject("summary").toString());
                        if (left) {
                            WidgetStore.setNotice(app, WidgetNotice.now(
                                WidgetNotice.PASSED, title, res.optString("application_id", null)));
                        }
                    }
                } else {
                    failed(app, r.status, before, seq, token, apiBase);
                }
            } catch (IOException | JSONException e) {
                failed(app, 0, before, seq, token, apiBase);
            } finally {
                finish(app, pending);
            }
        });
    }

    static void undo(Context context, String applicationId, String title,
                     BroadcastReceiver.PendingResult pending) {
        Context app = context.getApplicationContext();
        String token = WidgetStore.token(app);
        String apiBase = WidgetStore.apiBase(app);
        if (!WidgetData.isSafeId(applicationId) || token == null || apiBase == null) {
            finish(app, pending);
            return;
        }
        // Mientras tanto se quita el "Deshacer", para que no se pulse dos veces.
        WidgetStore.setNotice(app, WidgetNotice.now(WidgetNotice.UNDONE, title, null));
        int seq = WidgetStore.nextSeq(app);
        WidgetUpdater.updateAll(app);

        WidgetApi.EXECUTOR.execute(() -> {
            try {
                JSONObject body = new JSONObject();
                body.put("application_id", applicationId);
                WidgetApi.Response r = WidgetApi.call("POST", apiBase, "/widget/undo", token, body.toString());
                if (r.ok()) {
                    if (WidgetStore.currentSeq(app) == seq) {
                        WidgetStore.save(app, new JSONObject(r.body).getJSONObject("summary").toString());
                    }
                } else {
                    failed(app, r.status, null, seq, token, apiBase);
                }
            } catch (IOException | JSONException e) {
                failed(app, 0, null, seq, token, apiBase);
            } finally {
                finish(app, pending);
            }
        });
    }

    /** Refresco en segundo plano (cada 30 min y al poner el widget), para que
     * la cola no se quede vieja aunque la app no se abra en días. */
    static void refresh(Context context, BroadcastReceiver.PendingResult pending) {
        Context app = context.getApplicationContext();
        String token = WidgetStore.token(app);
        String apiBase = WidgetStore.apiBase(app);
        if (token == null || apiBase == null) {
            finish(app, pending);
            return;
        }
        int seq = WidgetStore.currentSeq(app);
        WidgetApi.EXECUTOR.execute(() -> {
            try {
                fetchSummary(app, seq, token, apiBase);
            } finally {
                finish(app, pending);
            }
        });
    }

    /** Cerrar sesión: revoca la credencial en el servidor. La sesión de la
     * app ya no existe, así que se usa la propia credencial. */
    static void revoke(String token, String apiBase) {
        if (token == null || apiBase == null) return;
        WidgetApi.EXECUTOR.execute(() -> {
            try {
                WidgetApi.call("DELETE", apiBase, "/widget/token", token, null);
            } catch (IOException ignored) {
                // Sin red: se queda viva en el servidor hasta que este
                // teléfono pida otra (que revoca la anterior) o se cambie la
                // contraseña. En el teléfono ya no existe.
            }
        });
    }

    // ------------------------------------------------------------------

    private static void fetchSummary(Context app, int seq, String token, String apiBase) {
        try {
            WidgetApi.Response r = WidgetApi.call("GET", apiBase, "/widget/summary", token, null);
            if (r.ok() && WidgetStore.currentSeq(app) == seq) {
                WidgetStore.save(app, new JSONObject(r.body).toString());
            } else if (r.status == 401) {
                WidgetStore.unlink(app);
            }
        } catch (IOException | JSONException ignored) {
            // Se queda la última foto; el próximo refresco lo reintenta.
        }
    }

    private static void failed(Context app, int status, String before, int seq, String token, String apiBase) {
        String message;
        if (status == 401) {
            // Credencial revocada (otra sesión, contraseña nueva): ✕ / ✓
            // vuelven a abrir la app hasta que esta la reconecte.
            WidgetStore.unlink(app);
            message = app.getString(R.string.widget_error_relink);
        } else if (status == 404 || status == 400) {
            // Ya no estaba (decidida en la app, cerrada): se trae la cola real.
            message = app.getString(R.string.widget_error_gone);
            fetchSummary(app, seq, token, apiBase);
            WidgetStore.setNotice(app, WidgetNotice.now(WidgetNotice.ERROR, message, null));
            return;
        } else {
            message = app.getString(status == 0 ? R.string.widget_error_offline : R.string.widget_error_generic);
        }
        if (before != null && WidgetStore.currentSeq(app) == seq) {
            WidgetStore.save(app, before); // la tarjeta vuelve a su sitio
        }
        WidgetStore.setNotice(app, WidgetNotice.now(WidgetNotice.ERROR, message, null));
    }

    private static void finish(Context app, BroadcastReceiver.PendingResult pending) {
        WidgetUpdater.updateAll(app);
        if (pending != null) pending.finish();
    }
}
