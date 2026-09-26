-- Local mirror of the production setup: Django reads with a SELECT-only user,
-- the seed script writes as root.
CREATE USER 'dash_analytics'@'%' IDENTIFIED BY 'localpass';
GRANT SELECT ON *.* TO 'dash_analytics'@'%';
