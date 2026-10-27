-- One row per working day and calendar profile. To add n working days to a date, join the
-- date's workday_index from fact_calendar_day plus n.

select
    calendar_profile_id,
    workday_index,
    date
from {{ source('holiday_calendar', 'fact_calendar_day') }}
where is_workday
