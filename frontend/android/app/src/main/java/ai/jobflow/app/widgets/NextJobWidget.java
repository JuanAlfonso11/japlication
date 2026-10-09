package ai.jobflow.app.widgets;

import ai.jobflow.app.R;
import android.appwidget.AppWidgetManager;
import android.appwidget.AppWidgetProvider;
import android.content.Context;
import android.net.Uri;
import android.os.Bundle;
import android.view.View;
import android.widget.RemoteViews;

/**
 * Widget "Próxima vacante": la tarjeta de arriba del mazo de Home.
 *
 * ✕ y ✓ NO deciden desde aquí. Abren la app en `/?swipe=left|right&job=<id>`
 * y es Home quien trae esa tarjeta arriba y lanza el mismo vuelo que sus
 * botones (app/page.tsx). Así la decisión pasa siempre por el swipe, con su
 * "Deshacer", y el widget nunca necesita la sesión.
 */
public class NextJobWidget extends AppWidgetProvider {

    private static final int ACTION_OPEN = 0;
    private static final int ACTION_CARD = 1;
    private static final int ACTION_PASS = 2;
    private static final int ACTION_SAVE = 3;

    @Override
    public void onUpdate(Context context, AppWidgetManager manager, int[] appWidgetIds) {
        for (int id : appWidgetIds) {
            render(context, manager, id);
        }
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
            showEmpty(views, R.drawable.ic_widget_done,
                context.getString(R.string.widget_empty_done_title),
                context.getString(R.string.widget_empty_done_body));
            views.setOnClickPendingIntent(
                R.id.widget_root,
                WidgetLinks.open(context, "/discover", WidgetLinks.requestCode(appWidgetId, ACTION_OPEN))
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

        views.setTextViewText(R.id.brand_label, WidgetText.brandWithAge(context, data.updatedAt));
        views.setTextViewText(R.id.queue_chip, context.getString(R.string.widget_queue_chip, data.queueCount));
        views.setTextViewText(R.id.job_title, job.title);
        views.setTextViewText(R.id.job_meta, WidgetText.joinNonEmpty(" · ", job.company, job.place));

        if (job.score == null) {
            views.setViewVisibility(R.id.match_row, View.GONE);
        } else {
            views.setViewVisibility(R.id.match_row, View.VISIBLE);
            views.setProgressBar(R.id.match_bar, 100, job.score, false);
            views.setTextViewText(R.id.match_label, context.getString(R.string.widget_match, job.score));
        }

        String id = Uri.encode(job.id);
        views.setOnClickPendingIntent(R.id.job_card,
            WidgetLinks.open(context, "/jobs/" + id, WidgetLinks.requestCode(appWidgetId, ACTION_CARD)));
        views.setOnClickPendingIntent(R.id.btn_pass,
            WidgetLinks.open(context, "/?swipe=left&job=" + id, WidgetLinks.requestCode(appWidgetId, ACTION_PASS)));
        views.setOnClickPendingIntent(R.id.btn_save,
            WidgetLinks.open(context, "/?swipe=right&job=" + id, WidgetLinks.requestCode(appWidgetId, ACTION_SAVE)));
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
