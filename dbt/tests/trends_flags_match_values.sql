-- The YES/NO flags agree with the columns they describe, a character always makes the row
-- Branded and a row with neither brand nor character is never Branded. Returns the offending rows.
select keyword_str, date_dte, brand_str, character_str, has_brand_str, has_character_str, branded_str
from {{ ref('trends') }}
where (brand_str is not null) <> (has_brand_str = 'YES')
   or (character_str is not null) <> (has_character_str = 'YES')
   or (franchise_n1_str is not null) <> (has_franchise_n1_str = 'YES')
   or (character_str is not null and branded_str <> 'Branded')
   or (brand_str is null and character_str is null and branded_str = 'Branded')
