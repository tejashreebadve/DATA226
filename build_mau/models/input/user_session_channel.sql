SELECT
userId,
sessionId,
channel
FROM {{ source('RAW', 'user_session_channel') }}
WHERE sessionId IS NOT NULL