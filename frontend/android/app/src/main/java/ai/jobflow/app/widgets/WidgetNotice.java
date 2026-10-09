package ai.jobflow.app.widgets;

import org.json.JSONException;
import org.json.JSONObject;

/**
 * El aviso corto que el widget enseña arriba tras un toque: lo mismo que la
 * app enseña bajo el mazo ("Pasaste X · Deshacer", "Guardado en tu
 * pipeline"), o por qué no se pudo.
 */
final class WidgetNotice {

    static final String PASSED = "passed";
    static final String SAVED = "saved";
    static final String UNDONE = "undone";
    static final String ERROR = "error";

    final String kind;
    /** Título de la vacante, o el mensaje de error. */
    final String text;
    /** Solo en PASSED, cuando el servidor ya confirmó: lo que deshace "Deshacer". */
    final String applicationId;
    final long at;

    WidgetNotice(String kind, String text, String applicationId, long at) {
        this.kind = kind;
        this.text = text == null ? "" : text;
        this.applicationId = applicationId;
        this.at = at;
    }

    static WidgetNotice now(String kind, String text, String applicationId) {
        return new WidgetNotice(kind, text, applicationId, System.currentTimeMillis());
    }

    boolean canUndo() {
        return PASSED.equals(kind) && WidgetData.isSafeId(applicationId);
    }

    String toJson() {
        try {
            JSONObject o = new JSONObject();
            o.put("kind", kind);
            o.put("text", text);
            if (applicationId != null) o.put("applicationId", applicationId);
            o.put("at", at);
            return o.toString();
        } catch (JSONException e) {
            return "{}";
        }
    }

    static WidgetNotice parse(String json) {
        if (json == null) return null;
        try {
            JSONObject o = new JSONObject(json);
            String kind = o.optString("kind", "");
            if (kind.isEmpty()) return null;
            String appId = o.has("applicationId") ? o.optString("applicationId", null) : null;
            return new WidgetNotice(kind, o.optString("text", ""), appId, o.optLong("at", 0L));
        } catch (JSONException e) {
            return null;
        }
    }
}
