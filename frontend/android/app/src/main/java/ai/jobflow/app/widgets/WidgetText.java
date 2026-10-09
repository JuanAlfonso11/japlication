package ai.jobflow.app.widgets;

import ai.jobflow.app.R;
import android.content.Context;

/** Textos compartidos por los dos widgets. */
final class WidgetText {

    private static final long MINUTE = 60_000L;
    private static final long HOUR = 60 * MINUTE;
    private static final long DAY = 24 * HOUR;

    private WidgetText() {}

    /** "JobPilot", o "JobPilot · hace 3 h" cuando la foto tiene más de una
     * hora: así se nota que hay que abrir la app para refrescarla, en vez
     * de mostrar una cola vieja como si fuera la de ahora. */
    static String brandWithAge(Context context, long updatedAt) {
        String brand = context.getString(R.string.widget_brand);
        String age = age(context, updatedAt, System.currentTimeMillis());
        return age == null ? brand : brand + " · " + age;
    }

    static String age(Context context, long updatedAt, long now) {
        if (updatedAt <= 0) return null;
        long elapsed = now - updatedAt;
        if (elapsed < HOUR) return null;
        if (elapsed < DAY) return context.getString(R.string.widget_age_hours, (int) (elapsed / HOUR));
        return context.getString(R.string.widget_age_days, (int) (elapsed / DAY));
    }

    static String joinNonEmpty(String separator, String... parts) {
        StringBuilder out = new StringBuilder();
        for (String part : parts) {
            if (part == null || part.trim().isEmpty()) continue;
            if (out.length() > 0) out.append(separator);
            out.append(part.trim());
        }
        return out.toString();
    }
}
