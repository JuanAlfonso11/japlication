package ai.jobflow.app.widgets;

import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URI;
import java.net.URISyntaxException;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

/**
 * Las llamadas del widget a /widget/* (backend app/api/v1/routers/widget.py),
 * con su propia credencial en `X-Widget-Token`. Nunca usa la sesión de la app.
 *
 * Un solo hilo para todas: los toques se mandan en el mismo orden en que se
 * hicieron, así que dos ✕ seguidos no pueden llegar al revés.
 */
final class WidgetApi {

    static final ExecutorService EXECUTOR = Executors.newSingleThreadExecutor();

    private static final int CONNECT_TIMEOUT_MS = 6_000;
    private static final int READ_TIMEOUT_MS = 8_000;
    private static final int MAX_BODY = 64 * 1024;

    static final class Response {
        final int status;
        final String body;

        Response(int status, String body) {
            this.status = status;
            this.body = body;
        }

        boolean ok() {
            return status >= 200 && status < 300;
        }
    }

    private WidgetApi() {}

    /** Solo se acepta la API de nuestro propio host, por https. Es lo que
     * manda la app web (API_BASE_URL); cualquier otra cosa se rechaza para
     * que la credencial no pueda acabar en otro servidor. */
    static boolean isTrustedApiBase(String apiBase) {
        if (apiBase == null || apiBase.length() > 300) return false;
        try {
            // java.net.URI y no android.net.Uri: así también se puede probar
            // en un test de JVM (WidgetActionsTest).
            URI uri = new URI(apiBase);
            return "https".equalsIgnoreCase(uri.getScheme())
                && uri.getUserInfo() == null
                && WidgetLinks.HOST.equalsIgnoreCase(uri.getHost());
        } catch (URISyntaxException e) {
            return false;
        }
    }

    static Response call(String method, String apiBase, String path, String token, String jsonBody)
            throws IOException {
        if (!isTrustedApiBase(apiBase)) throw new IOException("API no permitida");
        URL url = new URL(apiBase.replaceAll("/+$", "") + path);
        HttpURLConnection conn = (HttpURLConnection) url.openConnection();
        try {
            conn.setRequestMethod(method);
            conn.setConnectTimeout(CONNECT_TIMEOUT_MS);
            conn.setReadTimeout(READ_TIMEOUT_MS);
            conn.setUseCaches(false);
            conn.setInstanceFollowRedirects(false);
            conn.setRequestProperty("Accept", "application/json");
            conn.setRequestProperty("X-Widget-Token", token);
            if (jsonBody != null) {
                byte[] bytes = jsonBody.getBytes(StandardCharsets.UTF_8);
                conn.setDoOutput(true);
                conn.setRequestProperty("Content-Type", "application/json; charset=utf-8");
                conn.setFixedLengthStreamingMode(bytes.length);
                try (OutputStream out = conn.getOutputStream()) {
                    out.write(bytes);
                }
            }
            int status = conn.getResponseCode();
            InputStream in = status >= 400 ? conn.getErrorStream() : conn.getInputStream();
            return new Response(status, read(in));
        } finally {
            conn.disconnect();
        }
    }

    private static String read(InputStream in) throws IOException {
        if (in == null) return "";
        try (InputStream stream = in; ByteArrayOutputStream out = new ByteArrayOutputStream()) {
            byte[] buf = new byte[4096];
            int n;
            while ((n = stream.read(buf)) != -1) {
                if (out.size() + n > MAX_BODY) throw new IOException("Respuesta demasiado grande");
                out.write(buf, 0, n);
            }
            return new String(out.toByteArray(), StandardCharsets.UTF_8);
        }
    }
}
