package ai.jobflow.app.widgets;

import android.content.Context;
import android.os.Build;
import android.util.Log;
import androidx.annotation.NonNull;
import androidx.work.BackoffPolicy;
import androidx.work.Constraints;
import androidx.work.Data;
import androidx.work.ExistingWorkPolicy;
import androidx.work.NetworkType;
import androidx.work.OneTimeWorkRequest;
import androidx.work.OutOfQuotaPolicy;
import androidx.work.WorkManager;
import androidx.work.Worker;
import androidx.work.WorkerParameters;
import java.util.concurrent.TimeUnit;

/**
 * Donde el widget usa la red.
 *
 * Antes las llamadas salían de un hilo del propio BroadcastReceiver. Con la
 * app en segundo plano (que es siempre el caso al tocar el widget), Android
 * puede tenerle la red cortada —ahorro de batería, ahorro de datos, Doze— y
 * la petición moría sin llegar al servidor: "Sin conexión".
 *
 * WorkManager es la vía que Android da para esto: la tarea corre cuando hay
 * red de verdad, con prioridad (expedited) en Android 12+, y si falla se
 * reintenta en vez de perderse. Todo va en una sola cola única
 * ({@link #QUEUE}) para que los toques lleguen al servidor en orden.
 */
public final class WidgetWorker extends Worker {

    private static final String TAG = "JobPilotWidget";

    static final String QUEUE = "jobpilot-widget";
    static final String QUEUE_REFRESH = "jobpilot-widget-refresh";
    static final String QUEUE_REVOKE = "jobpilot-widget-revoke";
    static final String QUEUE_KEEPALIVE = "jobpilot-widget-keepalive";

    static final String KEY_OP = "op";
    static final String OP_DECIDE = "decide";
    static final String OP_UNDO = "undo";
    static final String OP_REFRESH = "refresh";
    static final String OP_REVOKE = "revoke";

    static final String KEY_JOB_ID = "job_id";
    static final String KEY_DECISION = "decision";
    static final String KEY_TITLE = "title";
    static final String KEY_APPLICATION_ID = "application_id";
    static final String KEY_SEQ = "seq";
    static final String KEY_TOKEN = "token";
    static final String KEY_API_BASE = "api_base";

    /** Intentos con error de red antes de rendirse y devolver la tarjeta. */
    static final int MAX_ATTEMPTS = 3;

    public WidgetWorker(@NonNull Context context, @NonNull WorkerParameters params) {
        super(context, params);
    }

    @NonNull
    @Override
    public Result doWork() {
        Context app = getApplicationContext();
        Data in = getInputData();
        boolean lastAttempt = getRunAttemptCount() + 1 >= MAX_ATTEMPTS;
        boolean retry;
        try {
            switch (String.valueOf(in.getString(KEY_OP))) {
                case OP_DECIDE:
                    retry = WidgetActions.sendDecision(app,
                        in.getString(KEY_JOB_ID), in.getString(KEY_DECISION),
                        in.getString(KEY_TITLE), in.getInt(KEY_SEQ, -1), lastAttempt);
                    break;
                case OP_UNDO:
                    retry = WidgetActions.sendUndo(app,
                        in.getString(KEY_APPLICATION_ID), in.getInt(KEY_SEQ, -1), lastAttempt);
                    break;
                case OP_REFRESH:
                    WidgetActions.fetchSummary(app, WidgetStore.currentSeq(app));
                    retry = false;
                    break;
                case OP_REVOKE:
                    retry = !WidgetActions.sendRevoke(in.getString(KEY_TOKEN), in.getString(KEY_API_BASE))
                        && !lastAttempt;
                    break;
                default:
                    retry = false;
            }
        } catch (RuntimeException e) {
            Log.w(TAG, "widget work failed", e);
            retry = false;
        } finally {
            WidgetUpdater.updateAll(app);
        }
        // Nunca Result.failure(): un fallo cancelaría los toques que vienen
        // detrás en la misma cola.
        return retry ? Result.retry() : Result.success();
    }

    // ------------------------------------------------------------ encolar

    /** ✕ / ✓ / Deshacer: detrás de lo que ya esté en la cola, en orden. */
    static void enqueueAction(Context context, Data input) {
        enqueue(context, QUEUE, ExistingWorkPolicy.APPEND_OR_REPLACE, request(input, true));
    }

    /** Refresco: si ya hay uno pendiente, sobra otro. */
    static void enqueueRefresh(Context context) {
        Data input = new Data.Builder().putString(KEY_OP, OP_REFRESH).build();
        enqueue(context, QUEUE_REFRESH, ExistingWorkPolicy.KEEP, request(input, false));
    }

    static void enqueueRevoke(Context context, String token, String apiBase) {
        Data input = new Data.Builder()
            .putString(KEY_OP, OP_REVOKE)
            .putString(KEY_TOKEN, token)
            .putString(KEY_API_BASE, apiBase)
            .build();
        enqueue(context, QUEUE_REVOKE, ExistingWorkPolicy.APPEND_OR_REPLACE, request(input, false));
    }

    private static void enqueue(Context context, String name, ExistingWorkPolicy policy,
                                OneTimeWorkRequest work) {
        WorkManager wm = WorkManager.getInstance(context.getApplicationContext());
        keepAlive(wm);
        wm.enqueueUniqueWork(name, policy, work);
    }

    /** Cerrar sesión: los toques sin mandar eran de la cuenta que se va. */
    static void cancelPending(Context context) {
        WorkManager wm = WorkManager.getInstance(context.getApplicationContext());
        wm.cancelUniqueWork(QUEUE);
        wm.cancelUniqueWork(QUEUE_REFRESH);
    }

    /**
     * Fallo conocido de WorkManager con widgets: cuando ya no le queda
     * trabajo, desactiva un receiver suyo; Android lo toma como "el paquete
     * cambió" y manda APPWIDGET_UPDATE → onUpdate → refresco → otra vez sin
     * trabajo → bucle. Un trabajo vacío a años vista lo deja siempre activo.
     */
    private static void keepAlive(WorkManager wm) {
        OneTimeWorkRequest idle = new OneTimeWorkRequest.Builder(WidgetWorker.class)
            .setInitialDelay(3650, TimeUnit.DAYS)
            .build();
        wm.enqueueUniqueWork(QUEUE_KEEPALIVE, ExistingWorkPolicy.KEEP, idle);
    }

    private static OneTimeWorkRequest request(Data input, boolean urgent) {
        OneTimeWorkRequest.Builder b = new OneTimeWorkRequest.Builder(WidgetWorker.class)
            .setInputData(input)
            .setConstraints(new Constraints.Builder()
                .setRequiredNetworkType(NetworkType.CONNECTED)
                .build())
            .setBackoffCriteria(BackoffPolicy.LINEAR, 10, TimeUnit.SECONDS)
            .addTag(QUEUE);
        // Expedited en Android 12+: corre al momento aunque la app esté en
        // segundo plano. En versiones anteriores WorkManager lo convertiría
        // en un servicio en primer plano con notificación; ahí no hace falta.
        if (urgent && Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            b.setExpedited(OutOfQuotaPolicy.RUN_AS_NON_EXPEDITED_WORK_REQUEST);
        }
        return b.build();
    }
}
