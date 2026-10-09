package ai.jobflow.app.widgets;

import ai.jobflow.app.R;
import android.appwidget.AppWidgetManager;
import android.appwidget.AppWidgetProvider;
import android.content.Context;
import android.os.Build;
import android.widget.RemoteViews;

/**
 * Widget "Tu pipeline": las cuatro cifras de la fila de chips de Home.
 * Cada celda abre su lista; las ofertas se pintan en ámbar cuando hay
 * alguna, igual que el resto de "mira aquí" de la app.
 */
public class PipelineWidget extends AppWidgetProvider {

    private static final int ACTION_ROOT = 0;
    private static final int ACTION_QUEUE = 1;
    private static final int ACTION_APPLIED = 2;
    private static final int ACTION_INTERVIEWING = 3;
    private static final int ACTION_OFFER = 4;

    @Override
    public void onUpdate(Context context, AppWidgetManager manager, int[] appWidgetIds) {
        for (int id : appWidgetIds) {
            render(context, manager, id);
        }
        // Cada 30 min y al ponerlo, igual que "Próxima vacante": por si solo
        // tienes puesto este.
        WidgetActions.refresh(context);
    }

    static void render(Context context, AppWidgetManager manager, int appWidgetId) {
        RemoteViews views = new RemoteViews(context.getPackageName(), R.layout.widget_pipeline);
        WidgetData data = WidgetStore.load(context);

        if (data == null) {
            // Sin sesión: rayas, no ceros. Un cero diría "no tienes nada".
            String none = context.getString(R.string.widget_no_value);
            views.setTextViewText(R.id.count_queue, none);
            views.setTextViewText(R.id.count_applied, none);
            views.setTextViewText(R.id.count_interviewing, none);
            views.setTextViewText(R.id.count_offer, none);
            setCountColor(context, views, R.id.count_offer, R.color.widget_text);
        } else {
            views.setTextViewText(R.id.count_queue, String.valueOf(data.queueCount));
            views.setTextViewText(R.id.count_applied, String.valueOf(data.applied));
            views.setTextViewText(R.id.count_interviewing, String.valueOf(data.interviewing));
            views.setTextViewText(R.id.count_offer, String.valueOf(data.offer));
            setCountColor(context, views, R.id.count_offer,
                data.offer > 0 ? R.color.widget_accent : R.color.widget_text);
        }

        views.setOnClickPendingIntent(R.id.widget_root,
            WidgetLinks.open(context, "/applications", WidgetLinks.requestCode(appWidgetId, ACTION_ROOT)));
        views.setOnClickPendingIntent(R.id.cell_queue,
            WidgetLinks.open(context, "/", WidgetLinks.requestCode(appWidgetId, ACTION_QUEUE)));
        views.setOnClickPendingIntent(R.id.cell_applied,
            WidgetLinks.open(context, "/applications?status=applied", WidgetLinks.requestCode(appWidgetId, ACTION_APPLIED)));
        views.setOnClickPendingIntent(R.id.cell_interviewing,
            WidgetLinks.open(context, "/applications?status=interviewing", WidgetLinks.requestCode(appWidgetId, ACTION_INTERVIEWING)));
        views.setOnClickPendingIntent(R.id.cell_offer,
            WidgetLinks.open(context, "/applications?status=offer", WidgetLinks.requestCode(appWidgetId, ACTION_OFFER)));

        manager.updateAppWidget(appWidgetId, views);
    }

    /** En Android 12+ se pasa el recurso, y el launcher resuelve claro u
     * oscuro él mismo cuando cambia el tema. Antes solo se puede pasar el
     * color ya resuelto con el tema de ahora. */
    private static void setCountColor(Context context, RemoteViews views, int viewId, int colorRes) {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            views.setColorStateList(viewId, "setTextColor", colorRes);
        } else {
            views.setTextColor(viewId, context.getColor(colorRes));
        }
    }
}
