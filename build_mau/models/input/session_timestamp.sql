SELECT
sessionId,
ts
FROM {{ source('RAW', 'session_timestamp') }}
WHERE sessionId IS NOT NULL