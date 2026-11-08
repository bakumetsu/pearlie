# Danbooru fixtures

These JSON files are hand-written from the documented Danbooru API shapes
(GET /posts.json and /posts/{id}.json). Fields include: id, md5, file_url,
large_file_url, preview_file_url, image_width, image_height, rating,
tag_string_general/artist/copyright/character/meta, and source. A missing
post is represented by HTTP 404 with the not_found.json body.

They are NOT recorded from the live site. Tests load them through an
injected httpx.MockTransport and never call danbooru.donmai.us.
