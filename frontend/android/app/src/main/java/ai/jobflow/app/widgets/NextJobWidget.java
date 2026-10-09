package ai.jobflow.app.widgets;

import ai.jobflow.app.R;
import android.app.PendingIntent;
import android.appwidget.AppWidgetManager;
import android.appwidget.AppWidgetProvider;
import android.content.Context;
import android.content.Intent;
import android.net.Uri;
import android.os.Bundle;
import android.view.View;
import android.widget.RemoteViews;

/**
 * Widget "Próxima vacante": la tarjeta de arriba del mazo de Home.
 *
 * Con su credencial (ver WidgetBridgePlugin.link), ✕ y ✓ deciden aquí mismo,
 * en segundo plano, sin abrir la app: la tarjeta avanza al instante y el
 * servidor recibe el mismo swipe que Home (WidgetActions). Tras pasar una
 * aparece "Deshacer", como en la app.
 *
 * Sin credencial todavía (recién actualizado, sin haber abierto la app),
 * ✕ y ✓ abren la app en `/?swipe=...` y Home hace el swipe: nunca se quedan
 * sin hacer nada.
 */
public class NextJobWidget extends AppWidgetProvider {

    private static final int ACTION_OPEN = 0;
    private static final int ACTION_CARD = 1;
    private static final int ACTION_PASS = 2;
    private static final int ACTION_SAVE = 3;
    private static final int ACTION_UNDO = 4;
    private static final int ACTION_CHIP = 5;

    @Override
    public void onReceive(Context context, Intent intent) {
        String action = intent.getAction();
        if (WidgetActions.ACTION_DECIDE.equals(action)) {
            WidgetActions.decide(
                context,
                intent.getStringExtra(WidgetActions.EXTRA_JOB_ID),
                intent.getStringExtra(WidgetActions.EXTRA_DECISION),
                intent.getStringExtra(WidgetActions.EXTRA_TITLE),
                goAsync()
            );
            return;
        }
        if (WidgetActions.ACTION_UNDO.equals(action)) {
            WidgetActions.undo(
                context,
                intent.getStringExtra(WidgetActions.EXTRA_APPLICATION_ID),
                intent.getStringExtra(WidgetActions.EXTRA_TITLE),
                goAsync()
            );
            return;
        }
        super.onReceive(context, intent);
    }

    @Override
    public void onUpdate(Context context, AppWidgetManager manager, int[] appWidgetIds) {
        for (int id : appWidgetIds) {
            render(context, manager, id);
        }
        // Cada 30 min (updatePeriodMillis) y al ponerlo: trae la cola real.
        WidgetActions.refresh(context, goAsync());
    }

    @Override
    public void onAppWidgetOptionsChanged(Context context, AppWidgetManager manager, int appWidgetId, Bundle newOptions) {
        // Al redimensionarlo: lo que cabe depende del alto.
        render(context, manager, appWidgetId);
    }

    static void render(Context context, AppWidgetManager manager, int appWidgetId) {
        RemoteViews views = new RemoteViews(context.getPackageName(), R.layout.widget_next_job);
        WidgetData data = WidgetStore.load(context);

        views.setOnClickPendingIntent(
            R.id.widget_root,
            WidgetLinks.open(context, "/", WidgetLinks.requestCode(appWidgetId, ACTION_OPEN))
        );

        if (data == null) {
            showEmpty(views, R.mipmap.ic_launcher_round,
                context.getString(R.string.widget_empty_signed_out_title),
                context.getString(R.string.widget_empty_signed_out_body));
        } else if (data.next == null) {
            WidgetNotice notice = WidgetStore.notice(context);
            String body = context.getString(R.string.widget_empty_done_body);
            // Si la que acabas de pasar era la última, el widget entero sirve
            // de "Deshacer" (y lo dice), para no perder esa opción.
            if (notice != null && notice.canUndo()) {
                body = context.getString(R.string.widget_notice_passed_tap, notice.text);
            }
            showEmpty(views, R.drawable.ic_widget_done, context.getString(R.string.widget_empty_done_title), body);
            views.setOnClickPendingIntent(
                R.id.widget_root,
                notice != null && notice.canUndo()
                    ? undoIntent(context, appWidgetId, notice)
                    : WidgetLinks.open(context, "/discover", WidgetLinks.requestCode(appWidgetId, ACTION_OPEN))
            );
        } else {
            showJob(context, views, data, appWidgetId);
            applySize(views, manager.getAppWidgetOptions(appWidgetId));
        }

        manager.updateAppWidget(appWidgetId, views);
    }

    private static void showEmpty(RemoteViews views, int iconRes, String title, String body) {
        views.setViewVisibility(R.id.job_content, View.GONE);
        views.setViewVisibility(R.id.empty_state, View.VISIBLE);
        views.setImageViewResource(R.id.empty_icon, iconRes);
        views.setTextViewText(R.id.empty_title, title);
        views.setTextViewText(R.id.empty_body, body);
    }

    private static void showJob(Context context, RemoteViews views, WidgetData data, int appWidgetId) {
        WidgetData.NextJob job = data.next;
        views.setViewVisibility(R.id.empty_state, View.GONE);
        views.setViewVisibility(R.id.job_content, View.VISIBLE);

        // Arriba: el aviso del último toque, o "JobPilot · hace X h".
        WidgetNotice notice = WidgetStore.notice(context);
        views.setTextViewText(R.id.brand_label,
            notice != null ? noticeText(context, notice) : WidgetText.brandWithAge(context, data.updatedAt));

        // El chip: "Deshacer" tras pasar una, si no "N en cola".
        if (notice != null && notice.canUndo()) {
            views.setTextViewText(R.id.queue_chip, context.getString(R.string.widget_undo));
            views.setOnClickPendingIntent(R.id.queue_chip, undoIntent(context, appWidgetId, notice));
        } else {
            views.setTextViewText(R.id.queue_chip, context.getString(R.string.widget_queue_chip, data.queueCount));
            views.setOnClickPendingIntent(R.id.queue_chip,
                WidgetLinks.open(context, "/", WidgetLinks.requestCode(appWidgetId, ACTION_CHIP)));
        }

        views.setTextViewText(R.id.job_title, job.title);
        views.setTextViewText(R.id.job_meta, WidgetText.joinNonEmpty(" · ", job.company, job.place));

        if (job.score == null) {
            views.setViewVisibility(R.id.match_row, View.GONE);
        } else {
            views.setViewVisibility(R.id.match_row, View.VISIBLE);
            views.setProgressBar(R.id.match_bar, 100, job.score, false);
            views.setTextViewText(R.id.match_label, context.getString(R.string.widget_match, job.score));
        }

        views.setOnClickPendingIntent(R.id.job_card,
            WidgetLinks.open(context, "/jobs/" + Uri.encode(job.id), WidgetLinks.requestCode(appWidgetId, ACTION_CARD)));

        boolean linked = WidgetStore.isLinked(context);
        views.setOnClickPendingIntent(R.id.btn_pass, linked
            ? decideIntent(context, appWidgetId, ACTION_PASS, job, "left")
            : WidgetLinks.open(context, "/?swipe=left&job=" + Uri.encode(job.id), WidgetLinks.requestCode(appWidgetId, ACTION_PASS)));
        views.setOnClickPendingIntent(R.id.btn_save, linked
            ? decideIntent(context, appWidgetId, ACTION_SAVE, job, "right")
            : WidgetLinks.open(context, "/?swipe=right&job=" + Uri.encode(job.id), WidgetLinks.requestCode(appWidgetId, ACTION_SAVE)));
    }

    private static String noticeText(Context context, WidgetNotice notice) {
        switch (notice.kind) {
            case WidgetNotice.PASSED:
                return context.getString(R.string.widget_notice_passed, notice.text);
            case WidgetNotice.SAVED:
                return context.getString(R.string.widget_notice_saved, notice.text);
            case WidgetNotice.UNDONE:
                return context.getString(R.string.widget_notice_undone, notice.text);
            default:
                return notice.text;
        }
    }

    /** Un broadcast a este mismo widget, no una Activity: así no se abre nada.
     * La URI distinta por vacante y decisión evita que Android reutilice el
     * PendingIntent de otra tarjeta con sus extras viejos. */
    private static PendingIntent decideIntent(Context context, int appWidgetId, int action,
                                              WidgetData.NextJob job, String decision) {
        Intent intent = new Intent(context, NextJobWidget.class)
            .setAction(WidgetActions.ACTION_DECIDE)
            .setData(Uri.parse("jobpilot-widget://decide/" + decision + "/" + job.id))
            .putExtra(WidgetActions.EXTRA_JOB_ID, job.id)
            .putExtra(WidgetActions.EXTRA_DECISION, decision)
            .putExtra(WidgetActions.EXTRA_TITLE, job.title);
        return PendingIntent.getBroadcast(context, WidgetLinks.requestCode(appWidgetId, action), intent,
            PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);
    }

    private static PendingIntent undoIntent(Context context, int appWidgetId, WidgetNotice notice) {
        Intent intent = new Intent(context, NextJobWidget.class)
            .setAction(WidgetActions.ACTION_UNDO)
            .setData(Uri.parse("jobpilot-widget://undo/" + notice.applicationId))
            .putExtra(WidgetActions.EXTRA_APPLICATION_ID, notice.applicationId)
            .putExtra(WidgetActions.EXTRA_TITLE, notice.text);
        return PendingIntent.getBroadcast(context, WidgetLinks.requestCode(appWidgetId, ACTION_UNDO), intent,
            PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);
    }

    /** En vertical Android informa el alto real como MAX_HEIGHT. Por debajo
     * de ~150dp no caben título a dos líneas, empresa, match y botones, así
     * que se va quitando de lo menos importante a lo más: los botones y el
     * título se quedan siempre. */
    private static void applySize(RemoteViews views, Bundle options) {
        int height = options == null ? 0 : options.getInt(AppWidgetManager.OPTION_APPWIDGET_MAX_HEIGHT, 0);
        if (height <= 0) return; // Launcher que no lo dice: diseño completo.
        boolean compact = height < 150;
        boolean tiny = height < 128;
        views.setInt(R.id.job_title, "setMaxLines", compact ? 1 : 2);
        views.setViewVisibility(R.id.job_meta, compact ? View.GONE : View.VISIBLE);
        if (tiny) views.setViewVisibility(R.id.match_row, View.GONE);
    }
}
