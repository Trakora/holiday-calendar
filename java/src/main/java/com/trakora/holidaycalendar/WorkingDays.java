package com.trakora.holidaycalendar;

import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.time.LocalDate;

/**
 * Working days per region from the Trakora holiday calendar. Regions are identified by
 * country and official code, e.g. {@code DE-09564000} for Nuremberg.
 *
 * <p>Reads two tables with DuckDB into memory once, a few megabytes, and answers from there.
 */
public final class WorkingDays implements AutoCloseable {

    public static final String BASE_URL = "https://data.trakora.com/holiday-calendar/v1";

    private final Connection connection;

    public WorkingDays() throws SQLException {
        this(BASE_URL);
    }

    /** @param baseUrl base URL of the holiday calendar, or a local folder with the same layout */
    public WorkingDays(String baseUrl) throws SQLException {
        connection = DriverManager.getConnection("jdbc:duckdb:");
        load("day", "calendar_profile_id, date, is_workday, workday_index", baseUrl + "/latest/fact_calendar_day.parquet");
        load("region_profile", "region_id, calendar_profile_id, valid_from, valid_until", baseUrl + "/latest/bridge_region_profile.parquet");
    }

    /** Whether the date is a working day in the region: not a weekend day and no public holiday. */
    public boolean isWorkday(String regionId, LocalDate date) throws SQLException {
        try (var query = connection.prepareStatement("""
                SELECT d.is_workday
                FROM day d JOIN region_profile r USING (calendar_profile_id)
                WHERE r.region_id = ? AND d.date = ? AND d.date BETWEEN r.valid_from AND r.valid_until
                """)) {
            query.setString(1, regionId);
            query.setObject(2, date);
            return single(query).getBoolean(1);
        }
    }

    /** The date {@code days} working days after {@code date} in the region. */
    public LocalDate addWorkdays(String regionId, LocalDate date, int days) throws SQLException {
        try (var query = connection.prepareStatement("""
                SELECT target.date
                FROM day start
                JOIN region_profile r
                  ON r.calendar_profile_id = start.calendar_profile_id
                 AND start.date BETWEEN r.valid_from AND r.valid_until
                JOIN day target
                  ON target.calendar_profile_id = start.calendar_profile_id
                 AND target.is_workday
                 AND target.workday_index = start.workday_index + ?
                WHERE r.region_id = ? AND start.date = ?
                """)) {
            query.setInt(1, days);
            query.setString(2, regionId);
            query.setObject(3, date);
            return single(query).getObject(1, LocalDate.class);
        }
    }

    @Override
    public void close() throws SQLException {
        connection.close();
    }

    private void load(String table, String columns, String parquet) throws SQLException {
        try (var statement = connection.prepareStatement(
                "CREATE TABLE " + table + " AS SELECT " + columns + " FROM read_parquet(?)")) {
            statement.setString(1, parquet);
            statement.execute();
        }
    }

    private static ResultSet single(PreparedStatement query) throws SQLException {
        var result = query.executeQuery();
        if (!result.next()) {
            throw new IllegalArgumentException("No data for this region and date");
        }
        return result;
    }
}
