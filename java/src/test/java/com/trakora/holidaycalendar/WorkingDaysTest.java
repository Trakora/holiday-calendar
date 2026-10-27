package com.trakora.holidaycalendar;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.nio.file.Path;
import java.time.LocalDate;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;

class WorkingDaysTest {

    private static final String BERLIN = "DE-11000000";
    private static final String STUTTGART = "DE-08111000";
    private static WorkingDays workingDays;

    @BeforeAll
    static void load() throws Exception {
        Path fixture = Path.of("../tests/fixture/holiday-calendar/v1").toAbsolutePath().normalize();
        workingDays = new WorkingDays(fixture.toString());
    }

    @AfterAll
    static void close() throws Exception {
        workingDays.close();
    }

    @Test
    void corpusChristiIsAHolidayInStuttgartButNotInBerlin() throws Exception {
        LocalDate corpusChristi = LocalDate.of(2027, 5, 27);
        assertTrue(workingDays.isWorkday(BERLIN, corpusChristi));
        assertFalse(workingDays.isWorkday(STUTTGART, corpusChristi));
    }

    @Test
    void addsWorkingDaysAroundHolidays() throws Exception {
        LocalDate ordered = LocalDate.of(2027, 5, 26);
        assertEquals(LocalDate.of(2027, 5, 27), workingDays.addWorkdays(BERLIN, ordered, 1));
        assertEquals(LocalDate.of(2027, 5, 28), workingDays.addWorkdays(STUTTGART, ordered, 1));
    }
}
