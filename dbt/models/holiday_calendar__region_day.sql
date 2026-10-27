-- Every region on every day. Filter early (by region_id or date), for Germany the full view
-- has about 100 million rows.

select
    r.region_id,
    r.region_code,
    r.name as region_name,
    r.district_name,
    f.*
from {{ source('holiday_calendar', 'bridge_region_profile') }} as b
join {{ source('holiday_calendar', 'dim_region') }} as r
    on r.region_id = b.region_id
join {{ source('holiday_calendar', 'fact_calendar_day') }} as f
    on f.calendar_profile_id = b.calendar_profile_id
    and f.date between b.valid_from and b.valid_until
