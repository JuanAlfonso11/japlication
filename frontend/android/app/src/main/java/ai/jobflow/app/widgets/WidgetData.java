package ai.jobflow.app.widgets;

import org.json.JSONException;
import org.json.JSONObject;

/**
 * La foto que la app le deja a los widgets (ver frontend/lib/widgets.ts,
 * `WidgetPayload`). Se lee de forma tolerante: un campo que falta o viene
 * raro deja su valor por defecto en vez de tumbar el widget, porque un
 * widget que dice "Problema al cargar el widget" es peor que uno con un
 * número en cero.
 */
final class WidgetData {

    static final class NextJob {
        final String id;
        final String title;
        final String company;
        final String place;
        /** 0-100, o null si todavía no hay match calculado. */
        final Integer score;

        NextJob(String id, String title, String company, String place, Integer score) {
            this.id = id;
            this.title = title;
            this.company = company;
            this.place = place;
            this.score = score;
        }
    }

    final long updatedAt;
    final int queueCount;
    final NextJob next;
    final int applied;
    final int interviewing;
    final int offer;

    private WidgetData(long updatedAt, int queueCount, NextJob next, int applied, int interviewing, int offer) {
        this.updatedAt = updatedAt;
        this.queueCount = queueCount;
        this.next = next;
        this.applied = applied;
        this.interviewing = interviewing;
        this.offer = offer;
    }

    /** null si no es un JSON de widget utilizable. */
    static WidgetData parse(String json) {
        if (json == null || json.isEmpty()) return null;
        try {
            JSONObject root = new JSONObject(json);
            NextJob next = null;
            JSONObject n = root.optJSONObject("next");
            if (n != null) {
                String id = n.optString("id", "");
                if (isSafeId(id)) {
                    Integer score = null;
                    if (n.has("score") && !n.isNull("score")) {
                        score = clamp(n.optInt("score", 0), 0, 100);
                    }
                    next = new NextJob(
                        id,
                        n.optString("title", ""),
                        n.optString("company", ""),
                        n.optString("place", ""),
                        score
                    );
                }
            }
            JSONObject p = root.optJSONObject("pipeline");
            return new WidgetData(
                root.optLong("updatedAt", 0L),
                Math.max(0, root.optInt("queueCount", 0)),
                next,
                p == null ? 0 : Math.max(0, p.optInt("applied", 0)),
                p == null ? 0 : Math.max(0, p.optInt("interviewing", 0)),
                p == null ? 0 : Math.max(0, p.optInt("offer", 0))
            );
        } catch (JSONException e) {
            return null;
        }
    }

    /** El id acaba dentro de una URL que abre la app; solo se acepta la
     * forma de un UUID (o algo igual de inocuo). */
    static boolean isSafeId(String id) {
        return id != null && id.matches("[A-Za-z0-9-]{1,64}");
    }

    private static int clamp(int value, int min, int max) {
        return Math.max(min, Math.min(max, value));
    }
}
