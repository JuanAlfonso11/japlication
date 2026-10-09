package ai.jobflow.app.widgets;

import android.appwidget.AppWidgetManager;
import android.content.ComponentName;
import android.content.Context;

/** Redibuja todos los widgets puestos con la última foto guardada. */
final class WidgetUpdater {

    private WidgetUpdater() {}

    static void updateAll(Context context) {
        Context app = context.getApplicationContext();
        AppWidgetManager manager = AppWidgetManager.getInstance(app);
        if (manager == null) return;
        for (int id : manager.getAppWidgetIds(new ComponentName(app, NextJobWidget.class))) {
            NextJobWidget.render(app, manager, id);
        }
        for (int id : manager.getAppWidgetIds(new ComponentName(app, PipelineWidget.class))) {
            PipelineWidget.render(app, manager, id);
        }
    }
}
