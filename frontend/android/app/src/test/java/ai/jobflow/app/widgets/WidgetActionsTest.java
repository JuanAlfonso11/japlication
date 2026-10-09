package ai.jobflow.app.widgets;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertNotNull;
import static org.junit.Assert.assertNull;
import static org.junit.Assert.assertTrue;

import org.junit.Test;

/** Lo que hace que ✕ / ✓ se sientan inmediatos y que la credencial del
 * widget no pueda salir hacia otro servidor. */
public class WidgetActionsTest {

    private static final String PAYLOAD =
        "{\"v\":1,\"updatedAt\":1,\"queueCount\":3,"
            + "\"next\":{\"id\":\"aaa-1\",\"title\":\"Primera\",\"company\":\"A\",\"place\":\"Remoto\",\"score\":90},"
            + "\"upcoming\":[{\"id\":\"bbb-2\",\"title\":\"Segunda\",\"company\":\"B\",\"place\":\"\",\"score\":80},"
            + "{\"id\":\"ccc-3\",\"title\":\"Tercera\",\"company\":\"C\",\"place\":\"\",\"score\":null}],"
            + "\"pipeline\":{\"applied\":1,\"interviewing\":0,\"offer\":0}}";

    @Test
    public void advanceShowsTheNextCardRightAway() {
        String once = WidgetStore.advance(PAYLOAD, "aaa-1");
        assertNotNull(once);
        WidgetData d = WidgetData.parse(once);
        assertEquals("bbb-2", d.next.id);
        assertEquals("Segunda", d.next.title);
        assertEquals(2, d.queueCount);
        assertEquals(1, d.applied); // el pipeline no cambia por pasar/guardar

        String twice = WidgetStore.advance(once, "bbb-2");
        assertEquals("ccc-3", WidgetData.parse(twice).next.id);

        String done = WidgetStore.advance(twice, "ccc-3");
        WidgetData empty = WidgetData.parse(done);
        assertNull(empty.next);
        assertEquals(0, empty.queueCount);
    }

    @Test
    public void advanceIgnoresATapOnACardThatIsNoLongerOnTop() {
        assertNull(WidgetStore.advance(PAYLOAD, "bbb-2"));
        assertNull(WidgetStore.advance(null, "aaa-1"));
        assertNull(WidgetStore.advance("no json", "aaa-1"));
    }

    @Test
    public void noticeRoundTripsAndOnlyAConfirmedPassCanBeUndone() {
        WidgetNotice pending = WidgetNotice.parse(WidgetNotice.now(WidgetNotice.PASSED, "Primera", null).toJson());
        assertNotNull(pending);
        assertEquals("Primera", pending.text);
        assertFalse(pending.canUndo()); // el servidor aún no devolvió el id

        WidgetNotice confirmed = WidgetNotice.parse(
            WidgetNotice.now(WidgetNotice.PASSED, "Primera", "5c347b19-9944-4dcd-aadb-7a85910a1536").toJson());
        assertTrue(confirmed.canUndo());

        WidgetNotice saved = WidgetNotice.now(WidgetNotice.SAVED, "Primera", "5c347b19-9944-4dcd-aadb-7a85910a1536");
        assertFalse(saved.canUndo()); // como en la app: solo se deshace un "pasar"

        assertNull(WidgetNotice.parse(null));
        assertNull(WidgetNotice.parse("{}"));
    }

    @Test
    public void credentialOnlyGoesToOurOwnHostOverHttps() {
        assertTrue(WidgetApi.isTrustedApiBase("https://jobpilot.tailb3d4c1.ts.net:8443/api/v1"));
        assertTrue(WidgetApi.isTrustedApiBase("https://jobpilot.tailb3d4c1.ts.net/api/v1"));
        assertFalse(WidgetApi.isTrustedApiBase("http://jobpilot.tailb3d4c1.ts.net/api/v1"));
        assertFalse(WidgetApi.isTrustedApiBase("https://evil.example.com/api/v1"));
        assertFalse(WidgetApi.isTrustedApiBase("https://jobpilot.tailb3d4c1.ts.net.evil.com/api/v1"));
        assertFalse(WidgetApi.isTrustedApiBase("https://user@jobpilot.tailb3d4c1.ts.net/api/v1"));
        assertFalse(WidgetApi.isTrustedApiBase(null));
        assertFalse(WidgetApi.isTrustedApiBase("no es una url"));
    }
}
