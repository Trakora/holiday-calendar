// Loads one table of the holiday calendar in Power BI or Excel, with column types from the manifest.
// Blank query named HolidayCalendar with this code, then one query per table:
//   = HolidayCalendar("fact_calendar_day")
(table as text) as table =>
    let
        Base = "https://data.trakora.com/holiday-calendar/v1/",
        Manifest = Json.Document(Web.Contents(Base, [RelativePath = "manifest.json"])),
        Columns = List.First(List.Select(Manifest[tables], each [name] = table))[columns],
        Types = [
            VARCHAR = type text,
            BOOLEAN = type logical,
            INTEGER = Int64.Type,
            BIGINT = Int64.Type,
            DOUBLE = type number,
            DATE = type date
        ],
        Source = Csv.Document(
            Web.Contents(Base, [RelativePath = "latest/" & table & ".csv"]),
            [Delimiter = ",", Encoding = 65001, QuoteStyle = QuoteStyle.Csv]
        ),
        Rows = Table.PromoteHeaders(Source, [PromoteAllScalars = true]),
        Typed = Table.TransformColumnTypes(
            Rows,
            List.Transform(Columns, each {[name], Record.Field(Types, [type])}),
            "en-US"
        )
    in
        Typed
