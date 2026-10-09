package ai.jobflow.app.widgets;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertNotNull;
import static org.junit.Assert.assertNull;
import static org.junit.Assert.assertTrue;

import org.junit.Test;

/** La foto que manda frontend/lib/widgets.ts, leída del lado Android. */
public class WidgetDataTest {

    private static final String FULL =
        "{\"v\":1,\"updatedAt\":1700000000000,\"queueCount\":12,"
            + "\"next\":{\"id\":\"5c347b19-9944-4dcd-aadb-7a85910a1536\",\"title\":\"Backend Engineer\","
            + "\"company\":\"Enveritas\",\"place\":\"Remoto\",\"score\":82},"
            + "\"pipeline\":{\"applied\":5,\"interviewing\":2,\"offer\":1}}";

    @Test
    public void readsTheFullPayload() {
        WidgetData d = WidgetData.parse(FULL);
        assertNotNull(d);
        assertEquals(1700000000000L, d.updatedAt);
        assertEquals(12, d.queueCount);
        assertEquals("Backend Engineer", d.next.title);
        assertEquals("Enveritas", d.next.company);
        assertEquals(Integer.valueOf(82), d.next.score);
        assertEquals(5, d.applied);
        assertEquals(2, d.interviewing);
        assertEquals(1, d.offer);
    }

    @Test
    public void emptyQueueHasNoNextJob() {
        WidgetData d = WidgetData.parse("{\"queueCount\":0,\"next\":null,\"pipeline\":{\"applied\":3}}");
        assertNotNull(d);
        assertNull(d.next);
        assertEquals(3, d.applied);
        assertEquals(0, d.offer);
    }

    @Test
    public void missingScoreStaysNullAndOutOfRangeIsClamped() {
        WidgetData noScore = WidgetData.parse("{\"next\":{\"id\":\"abc\",\"title\":\"x\",\"score\":null}}");
        assertNull(noScore.next.score);
        WidgetData big = WidgetData.parse("{\"next\":{\"id\":\"abc\",\"title\":\"x\",\"score\":250}}");
        assertEquals(Integer.valueOf(100), big.next.score);
    }

    @Test
    public void rejectsGarbageAndUnsafeIds() {
        assertNull(WidgetData.parse(null));
        assertNull(WidgetData.parse(""));
        assertNull(WidgetData.parse("no es json"));
        // Un id que no parece un UUID no llega nunca a una URL.
        WidgetData d = WidgetData.parse("{\"next\":{\"id\":\"../../x?swipe=right\",\"title\":\"x\"}}");
        assertNotNull(d);
        assertNull(d.next);
        assertTrue(WidgetData.isSafeId("5c347b19-9944-4dcd-aadb-7a85910a1536"));
        assertFalse(WidgetData.isSafeId(""));
        assertFalse(WidgetData.isSafeId("a/b"));
    }

    @Test
    public void negativeCountsBecomeZero() {
        WidgetData d = WidgetData.parse("{\"queueCount\":-4,\"pipeline\":{\"applied\":-1}}");
        assertEquals(0, d.queueCount);
        assertEquals(0, d.applied);
    }

    @Test
    public void joinSkipsEmptyParts() {
        assertEquals("Enveritas · Remoto", WidgetText.joinNonEmpty(" · ", "Enveritas", "", " Remoto "));
        assertEquals("Remoto", WidgetText.joinNonEmpty(" · ", null, "Remoto"));
        assertEquals("", WidgetText.joinNonEmpty(" · ", "", null));
    }
}
